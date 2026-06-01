import { apiGet } from "~/api/client";

export interface LandingStats {
  authors: number;
  works: number;
  xrefs: number;
}

export async function fetchLandingStats(signal?: AbortSignal): Promise<LandingStats> {
  return apiGet<LandingStats>("/api/landing/stats", signal);
}
