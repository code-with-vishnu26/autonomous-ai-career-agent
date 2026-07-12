import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SearchJobsPage } from "./SearchJobsPage";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

const PREFERENCES = {
  preferred_titles: [],
  alternative_titles: [],
  seniority: null,
  experience_years_min: null,
  experience_years_max: null,
  employment_types: [],
  work_mode: [],
  countries: [],
  states: [],
  cities: [],
  salary_min: null,
  salary_max: null,
  salary_currency: null,
  preferred_companies: [],
  blacklisted_companies: [],
  industries: [],
  visa_sponsorship_required: null,
  work_authorization: null,
  preferred_technologies: [],
  keywords_include: [],
  keywords_exclude: [],
  max_applications_per_day: null,
  require_human_confirmation: true,
  auto_tailor_resume: false,
  auto_generate_cover_letter: false,
  preferred_ats_providers: [],
  time_zone: null,
};

const RUN_PENDING = {
  id: "run-1",
  user_id: "u1",
  status: "PENDING",
  started_at: "2026-01-01T00:00:00Z",
  completed_at: null,
  new_count: 0,
  source_labels: [],
  errors: [],
};

const RUN_COMPLETED = {
  ...RUN_PENDING,
  status: "COMPLETED",
  completed_at: "2026-01-01T00:01:00Z",
  new_count: 2,
  source_labels: ["remotive"],
};

describe("SearchJobsPage", () => {
  it("saves preferences, triggers a run, and shows the completed count", async () => {
    let runPolls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/user/preferences") && method === "GET") {
          return jsonResponse(PREFERENCES);
        }
        if (url.endsWith("/user/preferences") && method === "PUT") {
          return jsonResponse({ ...PREFERENCES, preferred_titles: ["Backend Engineer"] });
        }
        if (url.endsWith("/discover") && method === "POST") {
          return jsonResponse(RUN_PENDING);
        }
        if (url.endsWith("/discover/run-1")) {
          runPolls += 1;
          return jsonResponse(runPolls >= 2 ? RUN_COMPLETED : RUN_PENDING);
        }
        if (url.includes("/discover/opportunities")) {
          return jsonResponse([]);
        }
        return jsonResponse([]);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<SearchJobsPage />);

    await waitFor(() => expect(screen.getByRole("button", { name: /search/i })).toBeEnabled());
    await user.type(screen.getByPlaceholderText("Software Engineer"), "Backend Engineer");
    await user.click(screen.getByRole("button", { name: /search/i }));

    await waitFor(() => expect(screen.getByText(/found 2 new opportunit/i)).toBeInTheDocument(), {
      timeout: 5000,
    });
  });

  it("shows an empty state when no opportunities have been discovered yet", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/user/preferences")) return jsonResponse(PREFERENCES);
        if (url.includes("/discover/opportunities")) return jsonResponse([]);
        return jsonResponse([]);
      }),
    );
    renderWithProviders(<SearchJobsPage />);

    expect(
      await screen.findByText(/no opportunities discovered yet/i),
    ).toBeInTheDocument();
  });
});
