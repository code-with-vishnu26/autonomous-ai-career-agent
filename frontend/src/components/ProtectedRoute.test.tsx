import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { ProtectedRoute } from "./ProtectedRoute";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

function renderProtected() {
  return render(
    <MemoryRouter initialEntries={["/secret"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<div>Login page</div>} />
          <Route element={<ProtectedRoute />}>
            <Route path="/secret" element={<div>Secret content</div>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute", () => {
  it("redirects to /login when there is no session", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ detail: "no session" }, 401)));
    renderProtected();
    await waitFor(() => expect(screen.getByText("Login page")).toBeInTheDocument());
  });

  it("renders the protected content when a session exists", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        jsonResponse({
          access_token: "tok",
          token_type: "bearer",
          user: {
            id: "u1",
            email: "user@example.com",
            display_name: null,
            role: "user",
            created_at: "2026-01-01T00:00:00Z",
          },
        }),
      ),
    );
    renderProtected();
    await waitFor(() => expect(screen.getByText("Secret content")).toBeInTheDocument());
  });
});
