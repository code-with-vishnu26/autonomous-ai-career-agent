import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NotificationsPage } from "./NotificationsPage";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

const NOTIFICATIONS = [
  {
    id: "n1",
    type: "SUCCESS",
    category: "resume_prepared",
    title: "Application prepared",
    message: "Ready for review.",
    read_at: null,
    created_at: "2026-01-02T00:00:00Z",
  },
  {
    id: "n2",
    type: "INFO",
    category: "review_rejected",
    title: "Review rejected",
    message: "The review was rejected.",
    read_at: "2026-01-01T00:00:00Z",
    created_at: "2026-01-01T00:00:00Z",
  },
];

function stubFetch(notifications = NOTIFICATIONS) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/notifications")) return jsonResponse(notifications);
      return jsonResponse([]);
    }),
  );
}

describe("NotificationsPage", () => {
  it("renders every notification", async () => {
    stubFetch();
    renderWithProviders(<NotificationsPage />);

    expect(await screen.findByText("Application prepared")).toBeInTheDocument();
    expect(await screen.findByText("Review rejected")).toBeInTheDocument();
  });

  it("filters to unread only", async () => {
    stubFetch();
    const user = userEvent.setup();
    renderWithProviders(<NotificationsPage />);

    await screen.findByText("Application prepared");
    await user.selectOptions(screen.getByRole("combobox"), "unread");

    expect(screen.getByText("Application prepared")).toBeInTheDocument();
    expect(screen.queryByText("Review rejected")).not.toBeInTheDocument();
  });

  it("filters by search text", async () => {
    stubFetch();
    const user = userEvent.setup();
    renderWithProviders(<NotificationsPage />);

    await screen.findByText("Application prepared");
    await user.type(
      screen.getByPlaceholderText(/search notifications/i),
      "rejected",
    );

    expect(screen.queryByText("Application prepared")).not.toBeInTheDocument();
    expect(screen.getByText("Review rejected")).toBeInTheDocument();
  });

  it("shows an empty state when nothing matches the filter", async () => {
    stubFetch([]);
    renderWithProviders(<NotificationsPage />);

    expect(await screen.findByText(/no notifications match/i)).toBeInTheDocument();
  });

  it("shows an error banner when the API is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("network down"))),
    );

    renderWithProviders(<NotificationsPage />);

    await waitFor(() =>
      expect(screen.getByText(/career-agent serve/i)).toBeInTheDocument(),
    );
  });
});
