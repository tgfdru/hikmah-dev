// Supabase Edge Function: mueen-draft
//
// The Sheykak app calls this function (supabase.functions.invoke("mueen-draft")) with the
// signed-in scholar's session. It checks who is calling, then forwards the draft request to
// the Mu'een API with the API key, which therefore never ships inside the app.
//
// Secrets (Supabase Dashboard -> Edge Functions -> Secrets, or `supabase secrets set`):
//   MUEEN_API_URL   https://mueen.fawazabdullah.dev
//   MUEEN_API_KEY   one of the keys in MUEEN_API_KEYS on the Mu'een server
// SUPABASE_URL and the project's publishable (anon) key are provided by Supabase automatically.
//
// Deploy: `supabase functions deploy mueen-draft --no-verify-jwt`.
// The project signs sessions with asymmetric (ES256) keys, which the gateway's legacy
// verify_jwt check rejects; the caller's session is verified below with Supabase Auth.

import { createClient, type SupabaseClient } from "npm:@supabase/supabase-js@2";

const API_URL = (Deno.env.get("MUEEN_API_URL") ?? "").replace(/\/+$/, "");
const API_KEY = Deno.env.get("MUEEN_API_KEY") ?? "";
const UPSTREAM_TIMEOUT_MS = 140_000; // a draft takes ~30-60 s; Supabase stops functions at 150 s (free plan)
const MAX_BODY_BYTES = 200_000;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

/** The project's publishable key: the legacy SUPABASE_ANON_KEY, or the newer SUPABASE_PUBLISHABLE_KEYS. */
function publishableKey(): string {
  const legacy = Deno.env.get("SUPABASE_ANON_KEY");
  if (legacy) return legacy;
  try {
    const keys = JSON.parse(Deno.env.get("SUPABASE_PUBLISHABLE_KEYS") ?? "{}") as Record<string, string>;
    return Object.values(keys)[0] ?? "";
  } catch {
    return "";
  }
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });
}

// ----------------------------------------------------------------------------------------
// Who may draft: an active scholar (profiles.role = 'scholar', status = 'active', as in
// Sheykak's own RLS rules) who is assigned to this question (question_assignments).
// Both queries run with the caller's own session, so Row Level Security applies.
async function isScholar(supabase: SupabaseClient, userId: string): Promise<boolean> {
  const { data, error } = await supabase.from("profiles").select("role, status").eq("id", userId).maybeSingle();
  return !error && data?.role === "scholar" && data?.status === "active";
}

async function canAnswer(supabase: SupabaseClient, questionId: string, userId: string): Promise<boolean> {
  const { data, error } = await supabase
    .from("question_assignments")
    .select("question_id")
    .eq("question_id", questionId)
    .eq("scholar_id", userId)
    .limit(1);
  return !error && (data?.length ?? 0) > 0;
}
// ----------------------------------------------------------------------------------------

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);
  if (!API_URL || !API_KEY) return json({ error: "not_configured" }, 500);

  const authHeader = req.headers.get("Authorization") ?? "";
  const token = authHeader.replace(/^Bearer\s+/i, "");
  if (!token) return json({ error: "unauthorized" }, 401);
  const supabase = createClient(Deno.env.get("SUPABASE_URL")!, publishableKey(), {
    global: { headers: { Authorization: authHeader } },
  });
  // Ask Supabase Auth about this exact token (works for ES256 and legacy HS256 sessions).
  const { data: { user }, error: authError } = await supabase.auth.getUser(token);
  if (!user) {
    console.error(`mueen auth: ${authError?.message ?? "no user"}`); // reason only, never the token
    return json({ error: "unauthorized" }, 401);
  }

  const raw = await req.text();
  if (raw.length > MAX_BODY_BYTES) return json({ error: "too_large" }, 413);
  let body: { questionId?: unknown; question?: unknown; messages?: unknown; scope?: unknown };
  try {
    body = JSON.parse(raw);
  } catch {
    return json({ error: "bad_request" }, 400);
  }
  if (typeof body.questionId !== "string" || !Array.isArray(body.messages) || typeof body.scope !== "object") {
    return json({ error: "bad_request" }, 400);
  }
  if (!(await isScholar(supabase, user.id))) {
    console.error("mueen forbidden: not an active scholar");
    return json({ error: "forbidden" }, 403);
  }
  if (!(await canAnswer(supabase, body.questionId, user.id))) {
    console.error("mueen forbidden: not assigned to this question");
    return json({ error: "forbidden" }, 403);
  }

  // One line per stage, never message text or keys: the dashboard log names any failure.
  const scope = body.scope as { kind?: unknown };
  console.log(`mueen draft start scope=${String(scope?.kind)} messages=${body.messages.length}`);
  const started = Date.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS);
  try {
    const upstream = await fetch(`${API_URL}/mueen/draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": API_KEY },
      // Only what the model needs; no user ids or names leave Supabase.
      body: JSON.stringify({
        questionId: body.questionId,
        question: body.question ?? null,
        messages: body.messages,
        scope: body.scope,
      }),
      signal: controller.signal,
    });
    const text = await upstream.text();
    console.log(`mueen draft upstream status=${upstream.status} ms=${Date.now() - started} bytes=${text.length}`);
    if (upstream.ok) {
      try {
        const parsed = JSON.parse(text) as Record<string, unknown>;
        if (!Array.isArray(parsed?.paragraphs) || typeof parsed?.status !== "string") {
          console.error(`mueen draft bad body keys=${Object.keys(parsed ?? {}).join(",")}`);
        }
      } catch {
        console.error("mueen draft bad body: not JSON");
      }
      return new Response(text, { status: 200, headers: { ...CORS, "Content-Type": "application/json" } });
    }
    console.error(`mueen api ${upstream.status}`); // status only: never log message text
    if (upstream.status === 422) return json({ error: "no_input" }, 422);
    if (upstream.status === 403) return json({ error: "service_ended" }, 503);
    return json({ error: "unavailable" }, 502);
  } catch (err) {
    const timedOut = err instanceof DOMException && err.name === "AbortError";
    const host = (() => {
      try {
        return new URL(API_URL).host;
      } catch {
        return "invalid MUEEN_API_URL";
      }
    })();
    const e = err as Error;
    console.error(`mueen draft fetch failed host=${host} ms=${Date.now() - started} ${e?.name}: ${e?.message}`);
    return json({ error: timedOut ? "timeout" : "unavailable" }, timedOut ? 504 : 502);
  } finally {
    clearTimeout(timer);
  }
});
