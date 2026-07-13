/**
 * `/user/master-profile` (Phase 64, ADR-0082) -- the dashboard's per-user
 * analogue of the CLI's file-based `MasterProfile` loader.
 */

import { apiFetchJson } from "./http";
import type { MasterProfile, MasterProfileUpdate } from "@/types/api";

export const masterProfileApi = {
  get: () => apiFetchJson<MasterProfile | null>("/user/master-profile"),
  update: (profile: MasterProfileUpdate) =>
    apiFetchJson<MasterProfile>("/user/master-profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profile),
    }),
};
