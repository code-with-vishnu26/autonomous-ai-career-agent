import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SubmissionQueuePage } from "./SubmissionQueuePage";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

const APPROVED_REVIEW = {
  id: "review-1",
  application_session_id: "sess-1",
  company: "Acme Corp",
  job_title: "Backend Engineer",
  provider: "greenhouse",
  approval_status: "APPROVED",
  review_notes: null,
  created_at: "2026-01-01T00:00:00Z",
  approved_at: "2026-01-01T00:00:00Z",
};

describe("SubmissionQueuePage", () => {
  it("prepares, awaits confirmation, and confirms a submission", async () => {
    let statusPolls = 0;
    let confirmed = false;
    const onConfirm = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/reviews")) return jsonResponse([APPROVED_REVIEW]);
        if (url.endsWith("/api/submissions")) return jsonResponse([]);
        if (url.endsWith("/submissions/prepare") && method === "POST") {
          return jsonResponse({
            token: "tok-1",
            status: "PREPARING",
            company: null,
            job_title: null,
            error: null,
            result_id: null,
          });
        }
        if (url.endsWith("/submissions/prepare/tok-1")) {
          statusPolls += 1;
          const status = confirmed
            ? "DONE"
            : statusPolls >= 2
              ? "AWAITING_CONFIRMATION"
              : "PREPARING";
          return jsonResponse({
            token: "tok-1",
            status,
            company: "Acme Corp",
            job_title: "Backend Engineer",
            error: null,
            result_id: confirmed ? "sub-1" : null,
          });
        }
        if (url.endsWith("/submissions/tok-1/confirm") && method === "POST") {
          confirmed = true;
          onConfirm(JSON.parse(String(init?.body)));
          return jsonResponse({
            token: "tok-1",
            status: "DONE",
            company: "Acme Corp",
            job_title: "Backend Engineer",
            error: null,
            result_id: "sub-1",
          });
        }
        return jsonResponse([]);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<SubmissionQueuePage />);

    expect(await screen.findByText("Backend Engineer")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^submit$/i }));

    expect(
      await screen.findByText(
        /every precondition holds\. confirm the real submission\?/i,
        {},
        { timeout: 5000 },
      ),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /confirm submit/i }));

    await waitFor(() =>
      expect(onConfirm).toHaveBeenCalledWith({ approved: true }),
    );
    expect(await screen.findByText(/done — see recorded attempts below/i)).toBeInTheDocument();
  });

  it("shows an empty ready state when nothing is approved yet", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/reviews")) return jsonResponse([]);
        if (url.endsWith("/api/submissions")) return jsonResponse([]);
        return jsonResponse([]);
      }),
    );
    renderWithProviders(<SubmissionQueuePage />);

    expect(
      await screen.findByText(/no approved applications waiting/i),
    ).toBeInTheDocument();
  });
});
