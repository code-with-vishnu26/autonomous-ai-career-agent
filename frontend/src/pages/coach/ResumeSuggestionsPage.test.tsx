import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResumeSuggestionsPage } from "./ResumeSuggestionsPage";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

describe("ResumeSuggestionsPage", () => {
  it("shows verified suggestions and lets the user mark accept/reject locally", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        jsonResponse([
          {
            original: "Wrote code.",
            suggested: "Built the API.",
            reason: "Stronger verb.",
            confidence: 0.9,
          },
        ]),
      ),
    );

    renderWithProviders(<ResumeSuggestionsPage />);

    await userEvent.type(
      screen.getByPlaceholderText(/paste your resume text/i),
      "Wrote code.",
    );
    await userEvent.type(
      screen.getByPlaceholderText(/paste the job description/i),
      "Looking for an API builder.",
    );
    await userEvent.click(screen.getByRole("button", { name: /suggest improvements/i }));

    await waitFor(() => expect(screen.getByText("Built the API.")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: /accept/i }));
    expect(screen.getByText(/nothing is applied automatically/i)).toBeInTheDocument();
  });
});
