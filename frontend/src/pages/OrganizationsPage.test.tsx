import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OrganizationsPage } from "./OrganizationsPage";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

const ORGS = [
  { id: "o1", name: "Acme Corp", slug: "acme-corp", role: "owner" },
];

describe("OrganizationsPage", () => {
  it("renders every organization the caller belongs to", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse(ORGS)));

    renderWithProviders(<OrganizationsPage />);

    expect(await screen.findByText("Acme Corp")).toBeInTheDocument();
    expect(screen.getByText("owner")).toBeInTheDocument();
  });

  it("shows an empty state when the caller has no organizations", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse([])));

    renderWithProviders(<OrganizationsPage />);

    expect(
      await screen.findByText(/don't belong to any organization/i),
    ).toBeInTheDocument();
  });

  it("creates a new organization from the form", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        calls.push({ url, init });
        if (url.endsWith("/organizations") && init?.method === "POST") {
          return jsonResponse({ id: "o2", name: "New Org", slug: "new-org", role: "owner" });
        }
        return jsonResponse(ORGS);
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<OrganizationsPage />);
    await screen.findByText("Acme Corp");

    await user.type(screen.getByPlaceholderText(/organization name/i), "New Org");
    await user.click(screen.getByRole("button", { name: /^create$/i }));

    await waitFor(() =>
      expect(
        calls.some((c) => c.url.endsWith("/organizations") && c.init?.method === "POST"),
      ).toBe(true),
    );
  });

  it("shows an error banner when the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("network down"))));

    renderWithProviders(<OrganizationsPage />);

    await waitFor(() =>
      expect(screen.getByText(/career-agent serve/i)).toBeInTheDocument(),
    );
  });
});
