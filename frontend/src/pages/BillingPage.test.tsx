import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BillingPage } from "./BillingPage";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

const PLANS = [
  { id: "free", name: "Free", monthly_price_cents: 0, max_seats: 3, features: [] },
  { id: "pro", name: "Pro", monthly_price_cents: 4900, max_seats: 15, features: ["view_analytics"] },
];

const SUBSCRIPTION = {
  organization_id: "o1",
  plan_id: "free",
  status: "ACTIVE",
  current_period_end: "2027-01-01T00:00:00Z",
};

function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/billing/plans")) return jsonResponse(PLANS);
      if (url.includes("/usage")) return jsonResponse([{ metric: "seats", count: 1 }]);
      if (url.includes("/checkout") && init?.method === "POST") {
        return jsonResponse({
          checkout_url: "https://billing.example.invalid/checkout/o1/pro",
          subscription: { ...SUBSCRIPTION, plan_id: "pro" },
        });
      }
      if (url.match(/\/billing\/o1$/)) return jsonResponse(SUBSCRIPTION);
      return jsonResponse({});
    }),
  );
}

function renderBillingPage() {
  return renderWithProviders(<BillingPage />, {
    route: "/organizations/o1/billing",
    path: "/organizations/:organizationId/billing",
  });
}

describe("BillingPage", () => {
  it("renders the current plan and every available plan", async () => {
    stubFetch();
    renderBillingPage();

    expect(await screen.findByText("free")).toBeInTheDocument();
    expect(screen.getByText("Pro")).toBeInTheDocument();
  });

  it("renders live seat usage", async () => {
    stubFetch();
    renderBillingPage();

    expect(await screen.findByText("seats")).toBeInTheDocument();
  });

  it("switches plan via checkout", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        calls.push({ url, init });
        if (url.endsWith("/billing/plans")) return jsonResponse(PLANS);
        if (url.includes("/usage")) return jsonResponse([]);
        if (url.includes("/checkout") && init?.method === "POST") {
          return jsonResponse({
            checkout_url: "https://billing.example.invalid/checkout/o1/pro",
            subscription: { ...SUBSCRIPTION, plan_id: "pro" },
          });
        }
        if (url.match(/\/billing\/o1$/)) return jsonResponse(SUBSCRIPTION);
        return jsonResponse({});
      }),
    );
    const user = userEvent.setup();

    renderBillingPage();
    await screen.findByText("Pro");

    await user.click(screen.getByRole("button", { name: /switch/i }));

    await waitFor(() =>
      expect(calls.some((c) => c.url.includes("/checkout"))).toBe(true),
    );
  });
});
