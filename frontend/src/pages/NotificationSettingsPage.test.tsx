import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NotificationSettingsPage } from "./NotificationSettingsPage";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

const DEFAULT_SETTINGS = {
  enable_email: false,
  enable_browser: true,
  enable_in_app: true,
  enable_reminders: true,
  enable_digests: true,
  quiet_hours_start: null,
  quiet_hours_end: null,
  timezone: "UTC",
  daily_digest_time: "08:00:00",
  weekly_digest_day: "mon",
  categories: [],
  webhook_configured: false,
};

describe("NotificationSettingsPage", () => {
  it("renders the caller's current preferences", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/notification-settings")) return jsonResponse(DEFAULT_SETTINGS);
        return jsonResponse({});
      }),
    );

    renderWithProviders(<NotificationSettingsPage />);

    expect(await screen.findByText("In-app notifications")).toBeInTheDocument();
    expect(screen.getByText("not set")).toBeInTheDocument();
  });

  it("toggling a channel sends a PATCH with the new value", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        calls.push({ url, init });
        if (url.includes("/notification-settings")) {
          if (init?.method === "PATCH") {
            return jsonResponse({ ...DEFAULT_SETTINGS, enable_email: true });
          }
          return jsonResponse(DEFAULT_SETTINGS);
        }
        return jsonResponse({});
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<NotificationSettingsPage />);
    await screen.findByText("Email notifications");

    const emailToggle = screen
      .getByText("Email notifications")
      .closest("label")
      ?.querySelector("input[type=checkbox]");
    expect(emailToggle).toBeTruthy();
    await user.click(emailToggle as HTMLInputElement);

    await waitFor(() =>
      expect(calls.some((c) => c.url.includes("/notification-settings") && c.init?.method === "PATCH")).toBe(true),
    );
    const patchCall = calls.find((c) => c.init?.method === "PATCH");
    expect(JSON.parse(String(patchCall?.init?.body))).toEqual({ enable_email: true });
  });

  it("shows configured webhook status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => jsonResponse({ ...DEFAULT_SETTINGS, webhook_configured: true })),
    );

    renderWithProviders(<NotificationSettingsPage />);

    expect(await screen.findByText("configured")).toBeInTheDocument();
  });
});
