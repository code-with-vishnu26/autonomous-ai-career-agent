import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserNotifier } from "./BrowserNotifier";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

const UNREAD = [
  {
    id: "n1",
    type: "SUCCESS",
    category: "resume_prepared",
    title: "Prepared",
    message: "Ready for review.",
    read_at: null,
    created_at: "2026-01-01T00:00:00Z",
  },
];

class FakeNotification {
  static permission: NotificationPermission = "default";
  static requestPermission = vi.fn(async () => FakeNotification.permission);
  title: string;
  body?: string;

  constructor(title: string, options?: NotificationOptions) {
    this.title = title;
    this.body = options?.body;
    FakeNotification.instances.push(this);
  }

  static instances: FakeNotification[] = [];
}

afterEach(() => {
  FakeNotification.instances = [];
  FakeNotification.permission = "default";
  vi.unstubAllGlobals();
});

describe("BrowserNotifier", () => {
  it("shows a permission banner when permission is undecided", async () => {
    vi.stubGlobal("Notification", FakeNotification);
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse(UNREAD)));

    renderWithProviders(<BrowserNotifier />);

    expect(
      await screen.findByText(/enable browser notifications/i),
    ).toBeInTheDocument();
  });

  it("requests permission when Enable is clicked", async () => {
    vi.stubGlobal("Notification", FakeNotification);
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse(UNREAD)));
    const user = userEvent.setup();

    renderWithProviders(<BrowserNotifier />);
    await screen.findByText(/enable browser notifications/i);
    await user.click(screen.getByRole("button", { name: /enable/i }));

    expect(FakeNotification.requestPermission).toHaveBeenCalled();
  });

  it("renders nothing once permission is granted", async () => {
    FakeNotification.permission = "granted";
    vi.stubGlobal("Notification", FakeNotification);
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse(UNREAD)));

    const { container } = renderWithProviders(<BrowserNotifier />);

    await waitFor(() => expect(FakeNotification.instances.length).toBe(1));
    expect(container).toBeEmptyDOMElement();
    expect(FakeNotification.instances[0].title).toBe("Prepared");
  });

  it("renders nothing once permission is denied", async () => {
    FakeNotification.permission = "denied";
    vi.stubGlobal("Notification", FakeNotification);
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse(UNREAD)));

    const { container } = renderWithProviders(<BrowserNotifier />);

    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("degrades gracefully when the browser has no Notification API", async () => {
    vi.stubGlobal("Notification", undefined);
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse(UNREAD)));

    const { container } = renderWithProviders(<BrowserNotifier />);

    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});
