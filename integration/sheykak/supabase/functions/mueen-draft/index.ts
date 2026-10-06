// Supabase Edge Function: mueen-draft
//
// The Sheykak app calls this function (supabase.functions.invoke("mueen-draft")) with the
// signed-in scholar's session. It checks who is calling, then forwards the draft request to
// the Mu'een API with the API key, which therefore never ships inside the app.
//
// Secrets (Supabase Dashboard -> Edge Functions -> Secrets, or `supabase secrets set`):
//   MUEEN_API_URL   https://mueen.fawazabdullah.dev
//   MUEEN_API_KEY   one of the keys in MUEEN_API_KEYS on the Mu'een server
// SUPABASE_URL and SUPABASE_ANON_KEY are provided by Supabase automatically.
//
// Deploy: `supabase functions deploy mueen-draft` (JWT verification stays ON).

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

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });
}

// ----------------------------------------------------------------------------------------
// TO ADAPT: how Sheykak knows a user is a scholar, and that the scholar may answer
// this question. Both run with the caller's own session, so Row Level Security applies.
// The table and column names below are placeholders — replace them with the real ones.
async function isScholar(supabase: SupabaseClient, userId: string): Promise<boolean> {
  const { data, error } = await supabase.from("profiles").select("role").eq("id", userId).maybeSingle();
  return !error && data?.role === "scholar";
}

async function canAnswer(supabase: SupabaseClient, questionId: string): Promise<boolean> {
  const { data, error } = await supabase.from("questions").select("id").eq("id", questionId).maybeSingle();
  return !error && !!data;
}
// ----------------------------------------------------------------------------------------

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);
  if (!API_URL || !API_KEY) return json({ error: "not_configured" }, 500);

  const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: req.headers.get("Authorization") ?? "" } },
  });
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return json({ error: "unauthorized" }, 401);

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
  if (!(await isScholar(supabase, user.id))) return json({ error: "forbidden" }, 403);
  if (!(await canAnswer(supabase, body.questionId))) return json({ error: "forbidden" }, 403);

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
    if (upstream.ok) {
      return new Response(text, { status: 200, headers: { ...CORS, "Content-Type": "application/json" } });
    }
    console.error(`mueen api ${upstream.status}`); // status only: never log message text
    if (upstream.status === 422) return json({ error: "no_input" }, 422);
    if (upstream.status === 403) return json({ error: "service_ended" }, 503);
    return json({ error: "unavailable" }, 502);
  } catch (err) {
    const timedOut = err instanceof DOMException && err.name === "AbortError";
    return json({ error: timedOut ? "timeout" : "unavailable" }, timedOut ? 504 : 502);
  } finally {
    clearTimeout(timer);
  }
});
