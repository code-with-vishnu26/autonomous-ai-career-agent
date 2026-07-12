import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NotificationBell } from "./NotificationBell";
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

describe("NotificationBell", () => {
  it("shows the unread count badge", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/notifications/unread")) return jsonResponse(UNREAD);
        return jsonResponse([]);
      }),
    );

    renderWithProviders(<NotificationBell />);

    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
  });

  it("opens the drawer and lists unread notifications", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/notifications/unread")) return jsonResponse(UNREAD);
        return jsonResponse([]);
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<NotificationBell />);
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /notifications/i }));

    expect(await screen.findByText("Prepared")).toBeInTheDocument();
  });

  it("shows no unread badge when there are no unread notifications", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse([])));

    renderWithProviders(<NotificationBell />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /notifications \(0 unread\)/i })).toBeInTheDocument(),
    );
    expect(screen.queryByText("1")).not.toBeInTheDocument();
  });
});
