import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResumeImportPanel } from "./ResumeImportPanel";
import { renderWithProviders } from "@/test/render";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

function resumeFile(): File {
  return new File(["Ada Lovelace\nada@example.com\n"], "resume.txt", {
    type: "text/plain",
  });
}

describe("ResumeImportPanel", () => {
  it("uploads a résumé, confirms/rejects proposals, and shows the outcome", async () => {
    const confirmed: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/user/master-profile/import") && method === "POST") {
          return jsonResponse(
            {
              token: "tok-1",
              source_type: "text",
              proposals: [
                {
                  proposal_id: "p1",
                  field_path: "basics.name",
                  proposed_value: "Ada Lovelace",
                  evidence_text: "Ada Lovelace",
                  conflict_ids: [],
                },
                {
                  proposal_id: "p2",
                  field_path: "basics.email",
                  proposed_value: "ada@example.com",
                  evidence_text: "ada@example.com",
                  conflict_ids: [],
                },
              ],
            },
            202,
          );
        }
        if (url.endsWith("/user/master-profile/import/tok-1/confirm") && method === "POST") {
          const body = JSON.parse(String(init?.body));
          confirmed.push(body);
          return jsonResponse({
            results: [
              {
                proposal_id: "p1",
                field_path: "basics.name",
                proposed_value: "Ada Lovelace",
                outcome: "ADD",
                reason: "no existing value",
              },
              {
                proposal_id: "p2",
                field_path: "basics.email",
                proposed_value: "ada@example.com",
                outcome: "REJECT",
                reason: "rejected by caller",
              },
            ],
            profile_saved: true,
            missing_required_fields: [],
            profile: {
              version: "sha256:abc",
              basics: {
                name: "Ada Lovelace",
                email: "",
                phone: null,
                summary: null,
                location: null,
              },
              work: [],
              education: [],
              skills: [],
              projects: [],
              legal_status: { work_authorized_us: null, requires_sponsorship: null },
            },
          });
        }
        return jsonResponse(null);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<ResumeImportPanel />);

    await user.upload(screen.getByLabelText(/résumé file/i), resumeFile());

    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();

    await user.selectOptions(
      screen.getByLabelText(/decision for name: ada lovelace/i),
      "confirm",
    );
    await user.selectOptions(
      screen.getByLabelText(/decision for email: ada@example\.com/i),
      "reject",
    );
    await user.click(screen.getByRole("button", { name: /save 2 decisions/i }));

    expect(await screen.findByText(/profile updated from your résumé/i)).toBeInTheDocument();
    expect(screen.getByText("ADD")).toBeInTheDocument();
    expect(screen.getByText("REJECT")).toBeInTheDocument();

    const body = confirmed[0] as { decisions: { proposal_id: string; confirmed: boolean }[] };
    expect(body.decisions).toEqual(
      expect.arrayContaining([
        { proposal_id: "p1", confirmed: true },
        { proposal_id: "p2", confirmed: false },
      ]),
    );
  });

  it("only sends decisions the user actually made -- skipped proposals are omitted", async () => {
    const confirmed: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/user/master-profile/import") && method === "POST") {
          return jsonResponse({
            token: "tok-2",
            source_type: "text",
            proposals: [
              {
                proposal_id: "p1",
                field_path: "basics.name",
                proposed_value: "Ada Lovelace",
                evidence_text: "Ada Lovelace",
                conflict_ids: [],
              },
              {
                proposal_id: "p2",
                field_path: "skills",
                proposed_value: "Python",
                evidence_text: "Skills: Python",
                conflict_ids: [],
              },
            ],
          });
        }
        if (url.endsWith("/user/master-profile/import/tok-2/confirm") && method === "POST") {
          const body = JSON.parse(String(init?.body));
          confirmed.push(body);
          return jsonResponse({
            results: [],
            profile_saved: false,
            missing_required_fields: ["email"],
            profile: null,
          });
        }
        return jsonResponse(null);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<ResumeImportPanel />);

    await user.upload(screen.getByLabelText(/résumé file/i), resumeFile());
    await screen.findByText("Ada Lovelace");

    await user.selectOptions(screen.getByLabelText(/decision for skill: python/i), "confirm");
    await user.click(screen.getByRole("button", { name: /save 1 decision/i }));

    expect(await screen.findByText(/still needs: email/i)).toBeInTheDocument();
    const body = confirmed[0] as { decisions: { proposal_id: string; confirmed: boolean }[] };
    expect(body.decisions).toEqual([{ proposal_id: "p2", confirmed: true }]);
  });

  it("shows an honest message when no facts could be extracted", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => jsonResponse({ token: "tok-3", source_type: "text", proposals: [] })),
    );
    const user = userEvent.setup();
    renderWithProviders(<ResumeImportPanel />);

    await user.upload(screen.getByLabelText(/résumé file/i), resumeFile());

    expect(
      await screen.findByText(/no facts could be confidently extracted/i),
    ).toBeInTheDocument();
  });

  it("shows the upload error message on failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: "Unsupported file type" }), { status: 400 }),
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<ResumeImportPanel />);

    await user.upload(screen.getByLabelText(/résumé file/i), resumeFile());

    expect(await screen.findByText(/unsupported file type/i)).toBeInTheDocument();
  });
});
