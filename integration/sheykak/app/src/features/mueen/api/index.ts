/**
 * The active Mu'een service: the live client (Supabase Edge Function `mueen-draft`).
 * Set EXPO_PUBLIC_MUEEN_MOCK=1 to use the offline sample answer instead.
 */
import { httpMueenService } from "./http-service";
import { mockMueenService } from "./mock-service";
import type { MueenService } from "../types";

export const mueenService: MueenService =
  process.env.EXPO_PUBLIC_MUEEN_MOCK === "1" ? mockMueenService : httpMueenService;
