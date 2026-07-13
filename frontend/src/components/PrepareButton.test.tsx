import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PrepareButton } from "./PrepareButton";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

describe("PrepareButton", () => {
  it("triggers prepare, polls to DONE, then offers a Review link", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/prepare") && method === "POST") {
          return jsonResponse({ token: "tok-1", status: "PREPARING" }, 202);
        }
        if (url.endsWith("/prepare/tok-1")) {
          return jsonResponse({
            token: "tok-1",
            status: "DONE",
            application_session_id: "sess-1",
          });
        }
        return jsonResponse(null);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<PrepareButton opportunityId="opp-1" />);

    await user.click(screen.getByRole("button", { name: /prepare application/i }));

    const reviewLink = await screen.findByRole("link", { name: /review application/i });
    expect(reviewLink).toHaveAttribute("href", "/review");
  });

  it("shows the failure reason when preparation fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/prepare") && method === "POST") {
          return jsonResponse({ token: "tok-2", status: "PREPARING" }, 202);
        }
        if (url.endsWith("/prepare/tok-2")) {
          return jsonResponse({
            token: "tok-2",
            status: "FAILED",
            error: "No Master Profile yet -- complete onboarding first.",
          });
        }
        return jsonResponse(null);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<PrepareButton opportunityId="opp-1" />);

    await user.click(screen.getByRole("button", { name: /prepare application/i }));

    await waitFor(() =>
      expect(screen.getByText(/complete onboarding first/i)).toBeInTheDocument(),
    );
  });
});
