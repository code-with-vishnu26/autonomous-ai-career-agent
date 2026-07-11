import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import App from "./App";
import { renderWithProviders } from "./test/render";
import { NAV_ITEMS } from "./layouts/nav-items";

function emptyJsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/analytics/summary")) {
        return emptyJsonResponse({
          applications_by_status: {},
          reviews_by_status: {},
          submissions_by_status: {},
        });
      }
      if (url.includes("/api/settings")) {
        return emptyJsonResponse({ values: {}, configured_secrets: {} });
      }
      return emptyJsonResponse([]);
    }),
  );
});

describe("App", () => {
  it("renders every nav item in the sidebar", () => {
    renderWithProviders(<App />);
    for (const item of NAV_ITEMS) {
      expect(screen.getAllByText(item.label).length).toBeGreaterThan(0);
    }
  });

  it("renders the Dashboard heading at the root route", () => {
    renderWithProviders(<App />, { route: "/" });
    expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("renders the Settings heading at /settings", () => {
    renderWithProviders(<App />, { route: "/settings" });
    expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument();
  });
});
