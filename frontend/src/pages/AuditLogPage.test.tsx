import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { AuditLogPage } from "./AuditLogPage";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

const ENTRIES = [
  {
    id: "a1",
    user_id: "u1",
    action: "invitation_sent:a@example.com",
    result: "ok",
    ip_address: "127.0.0.1",
    created_at: "2026-01-01T00:00:00Z",
  },
];

function renderAuditLogPage() {
  return renderWithProviders(<AuditLogPage />, {
    route: "/organizations/o1/audit",
    path: "/organizations/:organizationId/audit",
  });
}

describe("AuditLogPage", () => {
  it("renders every recorded entry", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse(ENTRIES)));

    renderAuditLogPage();

    expect(await screen.findByText(/invitation_sent/i)).toBeInTheDocument();
    expect(screen.getByText("ok")).toBeInTheDocument();
  });

  it("shows an empty state with nothing recorded yet", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse([])));

    renderAuditLogPage();

    expect(await screen.findByText(/no recorded activity/i)).toBeInTheDocument();
  });

  it("shows an error banner when the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("network down"))));

    renderAuditLogPage();

    await waitFor(() =>
      expect(screen.getByText(/career-agent serve/i)).toBeInTheDocument(),
    );
  });
});
