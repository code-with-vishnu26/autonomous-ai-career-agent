import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProfileMatchPage } from "./ProfileMatchPage";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

describe("ProfileMatchPage", () => {
  it("scores the stored profile against a pasted JD", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        jsonResponse({
          profile_version: "sha256:abc",
          match: {
            match_score: 82,
            matched_keywords: [],
            missing_keywords: [{ keyword: "kubernetes", kind: "tool" }],
          },
          skill_gap: {
            qualifies_percent: 75,
            missing_skills: [
              { keyword: "kubernetes", kind: "tool", reason: "in the JD, not your profile" },
            ],
          },
        }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<ProfileMatchPage />);

    await user.type(screen.getByLabelText(/job description/i), "Backend role");
    await user.click(screen.getByRole("button", { name: /score my profile/i }));

    expect(await screen.findByText(/match score: 82/i)).toBeInTheDocument();
    expect(screen.getByText("kubernetes (tool)")).toBeInTheDocument();
  });

  it("prompts onboarding when the user has no profile yet (404)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        jsonResponse({ detail: "No Master Profile yet -- complete onboarding first." }, 404),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<ProfileMatchPage />);

    await user.type(screen.getByLabelText(/job description/i), "Backend role");
    await user.click(screen.getByRole("button", { name: /score my profile/i }));

    await waitFor(() =>
      expect(screen.getByRole("link", { name: /complete onboarding/i })).toBeInTheDocument(),
    );
  });
});
