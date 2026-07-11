import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import App from "./App";
import { renderWithProviders } from "./test/render";
import { NAV_ITEMS } from "./layouts/nav-items";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

const FAKE_USER = {
  id: "u1",
  email: "test@example.com",
  display_name: null,
  role: "user",
  created_at: "2026-01-01T00:00:00Z",
};

function mockAuthenticatedSession() {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/auth/refresh")) {
        return jsonResponse({
          access_token: "fake-access-token",
          token_type: "bearer",
          user: FAKE_USER,
        });
      }
      if (url.includes("/api/analytics/summary")) {
        return jsonResponse({
          applications_by_status: {},
          reviews_by_status: {},
          submissions_by_status: {},
        });
      }
      if (url.includes("/api/settings")) {
        return jsonResponse({ values: {}, configured_secrets: {} });
      }
      return jsonResponse([]);
    }),
  );
}

function mockNoSession() {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/auth/refresh")) {
        return jsonResponse({ detail: "no session" }, 401);
      }
      return jsonResponse([]);
    }),
  );
}

describe("App (authenticated)", () => {
  beforeEach(() => {
    mockAuthenticatedSession();
  });

  it("renders every nav item in the sidebar", async () => {
    renderWithProviders(<App />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument(),
    );
    for (const item of NAV_ITEMS) {
      expect(screen.getAllByText(item.label).length).toBeGreaterThan(0);
    }
  });

  it("renders the Dashboard heading at the root route", async () => {
    renderWithProviders(<App />, { route: "/" });
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument(),
    );
  });

  it("renders the Settings heading at /settings", async () => {
    renderWithProviders(<App />, { route: "/settings" });
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument(),
    );
  });
});

describe("App (no session)", () => {
  beforeEach(() => {
    mockNoSession();
  });

  it("redirects a protected route to the login page", async () => {
    renderWithProviders(<App />, { route: "/" });
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Log in" })).toBeInTheDocument(),
    );
  });
});
