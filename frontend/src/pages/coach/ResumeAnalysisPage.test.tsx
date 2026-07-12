import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResumeAnalysisPage } from "./ResumeAnalysisPage";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

describe("ResumeAnalysisPage", () => {
  it("submits resume/JD text and renders the real API response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        jsonResponse({
          ats_score: 80,
          matched_keywords: [{ keyword: "Python", kind: "hard" }],
          missing_keywords: [{ keyword: "Docker", kind: "hard" }],
          weak_bullets: [],
          formatting_issues: [],
        }),
      ),
    );

    renderWithProviders(<ResumeAnalysisPage />);

    await userEvent.type(
      screen.getByPlaceholderText(/paste your resume text/i),
      "I know Python.",
    );
    await userEvent.type(
      screen.getByPlaceholderText(/paste the job description/i),
      "Needs Python and Docker.",
    );
    await userEvent.click(screen.getByRole("button", { name: /analyze/i }));

    await waitFor(() =>
      expect(screen.getByText("ATS Score: 80 / 100")).toBeInTheDocument(),
    );
    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByText(/Docker \(hard\)/)).toBeInTheDocument();
  });
});
