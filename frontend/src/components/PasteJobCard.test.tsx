import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PasteJobCard } from "./PasteJobCard";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

describe("PasteJobCard", () => {
  it("submits the pasted job and offers a Review link on success", async () => {
    const posted: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/prepare/pasted") && method === "POST") {
          posted.push(JSON.parse(String(init?.body)));
          return jsonResponse({ token: "tok-1", status: "PREPARING" }, 202);
        }
        if (url.endsWith("/prepare/tok-1")) {
          return jsonResponse({
            token: "tok-1",
            status: "DONE",
            application_session_id: "sess-1",
          });
        }
        return jsonResponse(null);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<PasteJobCard />);

    await user.type(screen.getByLabelText(/job title/i), "Backend Engineer");
    await user.type(screen.getByLabelText(/^company/i), "Acme Corp");
    await user.type(screen.getByLabelText(/job description/i), "Python role.");
    await user.click(screen.getByRole("button", { name: /tailor for this job/i }));

    const reviewLink = await screen.findByRole("link", { name: /review application/i });
    expect(reviewLink).toHaveAttribute("href", "/review");

    const body = posted[0] as { title: string; company: string };
    expect(body.title).toBe("Backend Engineer");
    expect(body.company).toBe("Acme Corp");
  });
});
