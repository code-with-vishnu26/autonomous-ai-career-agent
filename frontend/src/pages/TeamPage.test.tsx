import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TeamPage } from "./TeamPage";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

const MEMBERS = [
  { user_id: "u1", email: "owner@example.com", display_name: "Owner", role: "owner" },
];

const INVITATIONS = [
  {
    id: "i1",
    email: "invitee@example.com",
    role: "member",
    status: "PENDING",
    created_at: "2026-01-01T00:00:00Z",
    expires_at: "2026-01-08T00:00:00Z",
  },
];

const ROLES = [
  { role: "owner", permissions: ["manage_users", "delete_organization"] },
  { role: "member", permissions: ["submit"] },
];

function stubFetch({ members = MEMBERS, invitations = INVITATIONS } = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/invitations")) return jsonResponse(invitations);
      if (url.includes("/api/roles")) return jsonResponse(ROLES);
      if (url.includes("/invite") && init?.method === "POST") {
        return jsonResponse({
          id: "i2",
          email: "new@example.com",
          role: "member",
          status: "PENDING",
          created_at: "2026-01-01T00:00:00Z",
          expires_at: "2026-01-08T00:00:00Z",
        });
      }
      if (url.match(/\/team\/o1$/)) return jsonResponse(members);
      return jsonResponse([]);
    }),
  );
}

function renderTeamPage() {
  return renderWithProviders(<TeamPage />, {
    route: "/organizations/o1/team",
    path: "/organizations/:organizationId/team",
  });
}

describe("TeamPage", () => {
  it("renders every member", async () => {
    stubFetch();
    renderTeamPage();

    expect(await screen.findByText("Owner")).toBeInTheDocument();
  });

  it("renders pending invitations with their status", async () => {
    stubFetch();
    renderTeamPage();

    expect(await screen.findByText("invitee@example.com")).toBeInTheDocument();
    expect(screen.getByText("PENDING")).toBeInTheDocument();
  });

  it("sends an invite from the form", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        calls.push({ url, init });
        if (url.includes("/invitations")) return jsonResponse(INVITATIONS);
        if (url.includes("/api/roles")) return jsonResponse(ROLES);
        if (url.endsWith("/team/o1/invite") && init?.method === "POST") {
          return jsonResponse({
            id: "i2",
            email: "new@example.com",
            role: "member",
            status: "PENDING",
            created_at: "2026-01-01T00:00:00Z",
            expires_at: "2026-01-08T00:00:00Z",
          });
        }
        if (url.match(/\/team\/o1$/)) return jsonResponse(MEMBERS);
        return jsonResponse([]);
      }),
    );
    const user = userEvent.setup();

    renderTeamPage();
    await screen.findByText("Owner");

    await user.type(
      screen.getByPlaceholderText(/email@example.com/i),
      "new@example.com",
    );
    await user.click(screen.getByRole("button", { name: /^invite$/i }));

    await waitFor(() =>
      expect(
        calls.some(
          (c) => c.url.endsWith("/team/o1/invite") && c.init?.method === "POST",
        ),
      ).toBe(true),
    );
  });

  it("shows an empty state when no invitations were ever sent", async () => {
    stubFetch({ invitations: [] });
    renderTeamPage();

    expect(await screen.findByText(/no invitations sent/i)).toBeInTheDocument();
  });
});
