import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { AcceptInvitePage } from "./AcceptInvitePage";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

describe("AcceptInvitePage", () => {
  it("shows an error when no token is present in the URL", async () => {
    renderWithProviders(<AcceptInvitePage />, { route: "/accept-invite" });

    expect(
      await screen.findByText(/no invitation token provided/i),
    ).toBeInTheDocument();
  });

  it("accepts the invitation and shows the resulting role", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        jsonResponse({
          user_id: "u1",
          email: "me@example.com",
          display_name: null,
          role: "recruiter",
        }),
      ),
    );

    renderWithProviders(<AcceptInvitePage />, {
      route: "/accept-invite?token=abc123",
    });

    expect(await screen.findByText("recruiter")).toBeInTheDocument();
  });

  it("shows the API's error message when accept fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        jsonResponse({ detail: "This invitation is no longer pending." }, 400),
      ),
    );

    renderWithProviders(<AcceptInvitePage />, {
      route: "/accept-invite?token=stale-token",
    });

    await waitFor(() =>
      expect(screen.getByText(/no longer pending/i)).toBeInTheDocument(),
    );
  });
});
