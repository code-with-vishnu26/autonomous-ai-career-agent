import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OnboardingWizardPage } from "./OnboardingWizardPage";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

function stubFetch(onPut: (body: unknown) => void, existingProfile: unknown = null) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/user/master-profile") && method === "GET") {
        return jsonResponse(existingProfile);
      }
      if (url.endsWith("/user/master-profile") && method === "PUT") {
        const body = JSON.parse(String(init?.body));
        onPut(body);
        return jsonResponse({ ...body, version: "sha256:abcdef0123456789" });
      }
      return jsonResponse(null);
    }),
  );
}

async function goToStep(user: ReturnType<typeof userEvent.setup>, times: number) {
  for (let i = 0; i < times; i += 1) {
    await user.click(screen.getByRole("button", { name: /^next$/i }));
  }
}

describe("OnboardingWizardPage", () => {
  it("starts at the Welcome step when no profile exists yet", async () => {
    stubFetch(vi.fn());
    renderWithProviders(<OnboardingWizardPage />);

    expect(await screen.findByText("Welcome")).toBeInTheDocument();
    expect(screen.getByText(/step 1 of 8/i)).toBeInTheDocument();
  });

  it("fills personal details, adds a work entry, and saves through to review", async () => {
    const onPut = vi.fn();
    stubFetch(onPut);
    const user = userEvent.setup();
    renderWithProviders(<OnboardingWizardPage />);

    await screen.findByText("Welcome");
    await goToStep(user, 1); // -> personal
    expect(screen.getByText("Personal Details")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/full name/i), "Ada Lovelace");
    await user.type(screen.getByLabelText(/^email/i), "ada@example.com");

    await goToStep(user, 1); // -> work
    expect(screen.getByText("Work Experience")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /add role/i }));
    await user.type(screen.getByLabelText(/company/i), "Acme");
    await user.type(screen.getByLabelText(/position/i), "Engineer");

    await goToStep(user, 5); // -> education, skills, projects, legal, review
    expect(screen.getByText(/step 8 of 8/i)).toBeInTheDocument();
    expect(screen.getByText("Summary")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /save profile/i }));

    await waitFor(() => expect(onPut).toHaveBeenCalled());
    const body = onPut.mock.calls[0][0] as { basics: { name: string; email: string } };
    expect(body.basics.name).toBe("Ada Lovelace");
    expect(body.basics.email).toBe("ada@example.com");
    expect(body).not.toHaveProperty("version");

    expect(await screen.findByText(/profile saved/i)).toBeInTheDocument();
  });

  it("pre-fills the form from an existing stored profile", async () => {
    stubFetch(vi.fn(), {
      version: "sha256:existing",
      basics: { name: "Grace Hopper", email: "grace@example.com", phone: null, summary: null, location: null },
      work: [],
      education: [],
      skills: [],
      projects: [],
      legal_status: { work_authorized_us: null, requires_sponsorship: null },
    });
    const user = userEvent.setup();
    renderWithProviders(<OnboardingWizardPage />);

    await screen.findByText("Welcome");
    await goToStep(user, 1);
    expect(await screen.findByDisplayValue("Grace Hopper")).toBeInTheDocument();
  });
});
