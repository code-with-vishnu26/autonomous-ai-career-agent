import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { DashboardPage } from "./DashboardPage";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

describe("DashboardPage", () => {
  it("renders real counts from the API responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/applications")) {
          return jsonResponse([
            {
              id: "s1",
              provider: "greenhouse",
              company: "Acme",
              job_title: "Engineer",
              url: "https://x.invalid",
              opportunity_id: "o1",
              status: "READY_FOR_REVIEW",
              resume_variant_id: null,
              cover_letter_body: null,
              filled_fields: [],
              detected_fields: [],
              uploaded_files: [],
              missing_fields: [],
              warnings: [],
              created_at: "2026-01-01T00:00:00Z",
            },
          ]);
        }
        if (url.includes("/api/analytics/summary")) {
          return jsonResponse({
            applications_by_status: { READY_FOR_REVIEW: 1 },
            reviews_by_status: { APPROVED: 1 },
            submissions_by_status: { SUBMITTED: 1 },
          });
        }
        return jsonResponse([]);
      }),
    );

    renderWithProviders(<DashboardPage />);

    await waitFor(() => expect(screen.getByText("Prepared")).toBeInTheDocument());
    expect(screen.getAllByText("1").length).toBeGreaterThan(0);
  });

  it("shows an error banner when the API is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("network down"))),
    );

    renderWithProviders(<DashboardPage />);

    await waitFor(() =>
      expect(screen.getByText(/career-agent serve/i)).toBeInTheDocument(),
    );
  });
});
