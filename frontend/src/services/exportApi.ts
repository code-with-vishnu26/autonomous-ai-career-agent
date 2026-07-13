/**
 * Excel download helpers (Phase 65, ADR-0083).
 *
 * These hit the GET-only `/export/*.xlsx` endpoints through `apiFetch`, so
 * the access token + refresh-on-401 logic is reused exactly as every JSON
 * call has it -- the only difference is the response is a binary workbook,
 * not JSON, so it's turned into an object URL and click-downloaded rather
 * than parsed.
 */

import { apiFetch } from "./http";

async function downloadXlsx(path: string, filename: string): Promise<void> {
  const response = await apiFetch(path);
  if (!response.ok) {
    throw new Error(`Download failed (HTTP ${response.status})`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

export const exportApi = {
  applications: () =>
    downloadXlsx("/export/applications.xlsx", "applications.xlsx"),
  submissions: () =>
    downloadXlsx("/export/submissions.xlsx", "submissions.xlsx"),
};
