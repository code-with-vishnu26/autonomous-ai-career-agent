/**
 * `/user/master-profile/import` (Phase 71, ADR-0089) -- the two-step
 * upload/review/confirm résumé-import flow, the web analogue of the CLI's
 * `import-cv`/`promote-cv`. `upload` sends a multipart file (no
 * `Content-Type` set here deliberately -- the browser generates the
 * correct `multipart/form-data; boundary=...` header itself; setting one
 * by hand would omit the boundary and break parsing). `confirm` is a plain
 * JSON POST, reusing `apiFetchJson` like every other mutation in this app.
 */

import { apiFetch, apiFetchJson } from "./http";
import type {
  CvImportConfirmResponse,
  CvImportProposalDecision,
  CvImportUploadResponse,
} from "@/types/api";

export const cvImportApi = {
  upload: async (file: File): Promise<CvImportUploadResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await apiFetch("/user/master-profile/import", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      let detail = `Résumé upload failed (HTTP ${response.status})`;
      try {
        const body = await response.json();
        if (body?.detail) detail = String(body.detail);
      } catch {
        // response body wasn't JSON -- keep the generic message
      }
      throw new Error(detail);
    }
    return (await response.json()) as CvImportUploadResponse;
  },

  confirm: (token: string, decisions: CvImportProposalDecision[]) =>
    apiFetchJson<CvImportConfirmResponse>(`/user/master-profile/import/${token}/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decisions }),
    }),
};
