import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AdminPage } from "./AdminPage";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

const ORGS = [{ id: "o1", name: "Acme Corp", slug: "acme-corp", member_count: 2 }];
const MEMBERS = [{ user_id: "u1", email: "a@example.com", role: "owner" }];

describe("AdminPage", () => {
  it("renders every organization on the platform", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse(ORGS)));

    renderWithProviders(<AdminPage />);

    expect(await screen.findByText("Acme Corp")).toBeInTheDocument();
    expect(screen.getByText(/2 member/i)).toBeInTheDocument();
  });

  it("loads members after selecting an organization", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/members")) return jsonResponse(MEMBERS);
        return jsonResponse(ORGS);
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<AdminPage />);
    await screen.findByText("Acme Corp");

    await user.click(screen.getByText("Acme Corp"));

    expect(await screen.findByText("a@example.com")).toBeInTheDocument();
  });
});
