/**
 * The live Mu'een service: calls the `mueen-draft` Supabase Edge Function with the
 * scholar's session. The function holds the Mu'een API key and forwards the request
 * (the key never ships in the app). A draft takes ~30-60 s.
 */
import { FunctionsFetchError, FunctionsHttpError } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";
import type { MueenDraft, MueenService } from "../types";

const TIMEOUT_MS = 150_000;

export type MueenDraftErrorCode =
  | "unauthorized" // not signed in
  | "forbidden" // not a scholar, or not this question's scholar
  | "no_input" // no asker text to answer
  | "timeout"
  | "network"
  | "unavailable"; // the Mu'een service failed or is not configured

export class MueenDraftError extends Error {
  constructor(
    readonly code: MueenDraftErrorCode,
    message?: string,
  ) {
    super(message ?? code);
    this.name = "MueenDraftError";
  }
}

function codeForStatus(status: number | undefined): MueenDraftErrorCode {
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 422) return "no_input";
  if (status === 504) return "timeout";
  return "unavailable";
}

export const httpMueenService: MueenService = {
  async generateDraft(request) {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new MueenDraftError("timeout")), TIMEOUT_MS);
    });
    try {
      const { data, error } = await Promise.race([
        supabase.functions.invoke<MueenDraft>("mueen-draft", { body: request }),
        timeout,
      ]);
      if (error) {
        if (error instanceof FunctionsHttpError) {
          throw new MueenDraftError(codeForStatus((error.context as Response | undefined)?.status), error.message);
        }
        throw new MueenDraftError(error instanceof FunctionsFetchError ? "network" : "unavailable", error.message);
      }
      if (!data || !Array.isArray(data.paragraphs)) {
        throw new MueenDraftError("unavailable", "malformed draft");
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  },
};
