import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReviewQueuePage } from "./ReviewQueuePage";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

const PENDING_SESSION = {
  id: "sess-1",
  provider: "greenhouse",
  company: "Acme Corp",
  job_title: "Backend Engineer",
  url: "https://boards.greenhouse.io/acme/jobs/1",
  opportunity_id: "opp-1",
  status: "READY_FOR_REVIEW",
  resume_variant_id: null,
  cover_letter_body: null,
  filled_fields: [],
  detected_fields: [],
  uploaded_files: [],
  missing_fields: [],
  warnings: [],
  created_at: "2026-01-01T00:00:00Z",
};

function stubFetch(onDecide: (body: unknown) => void) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/reviews/pending")) return jsonResponse([PENDING_SESSION]);
      if (url.endsWith("/api/resume-variants")) return jsonResponse([]);
      if (url.endsWith("/reviews/decide")) {
        onDecide(JSON.parse(String(init?.body)));
        return jsonResponse({
          id: "review-1",
          application_session_id: "sess-1",
          company: "Acme Corp",
          job_title: "Backend Engineer",
          provider: "greenhouse",
          approval_status: "APPROVED",
          review_notes: null,
          created_at: "2026-01-01T00:00:00Z",
          approved_at: "2026-01-01T00:00:00Z",
        });
      }
      if (url.endsWith("/reviews")) return jsonResponse([]);
      return jsonResponse([]);
    }),
  );
}

describe("ReviewQueuePage", () => {
  it("renders the pending session and requires an explicit confirm to approve", async () => {
    const onDecide = vi.fn();
    stubFetch(onDecide);
    const user = userEvent.setup();
    renderWithProviders(<ReviewQueuePage />);

    expect(await screen.findByText("Backend Engineer @ Acme Corp")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /approve/i }));
    expect(screen.getByText(/approve this application\?/i)).toBeInTheDocument();
    expect(onDecide).not.toHaveBeenCalled(); // clicking Approve alone must not decide anything

    await user.click(screen.getByRole("button", { name: /yes, confirm/i }));

    await waitFor(() =>
      expect(onDecide).toHaveBeenCalledWith({
        application_session_id: "sess-1",
        approved: true,
        notes: null,
      }),
    );
  });

  it("cancel leaves the session pending without deciding", async () => {
    const onDecide = vi.fn();
    stubFetch(onDecide);
    const user = userEvent.setup();
    renderWithProviders(<ReviewQueuePage />);

    await screen.findByText("Backend Engineer @ Acme Corp");
    await user.click(screen.getByRole("button", { name: /reject/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(screen.getByRole("button", { name: /reject/i })).toBeInTheDocument();
    expect(onDecide).not.toHaveBeenCalled();
  });

  it("shows an empty state when nothing is pending", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/reviews/pending")) return jsonResponse([]);
        return jsonResponse([]);
      }),
    );
    renderWithProviders(<ReviewQueuePage />);

    expect(await screen.findByText(/nothing waiting for review/i)).toBeInTheDocument();
  });
});
