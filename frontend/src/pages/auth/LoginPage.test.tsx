import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { ThemeProvider } from "@/context/ThemeProvider";
import { LoginPage } from "./LoginPage";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

function renderLoginPage() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <ThemeProvider>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<div>Dashboard placeholder</div>} />
          </Routes>
        </AuthProvider>
      </ThemeProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/auth/refresh")) return jsonResponse({ detail: "no session" }, 401);
      return jsonResponse({ detail: "not mocked" }, 404);
    }),
  );
});

describe("LoginPage", () => {
  it("navigates to the dashboard on a successful login", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/auth/refresh")) return jsonResponse({ detail: "no" }, 401);
        if (url.includes("/auth/login")) {
          return jsonResponse({
            access_token: "tok",
            token_type: "bearer",
            user: {
              id: "u1",
              email: "user@example.com",
              display_name: null,
              role: "user",
              created_at: "2026-01-01T00:00:00Z",
            },
          });
        }
        return jsonResponse({ detail: "not mocked" }, 404);
      }),
    );

    renderLoginPage();
    await waitFor(() => screen.getByLabelText(/email/i));

    await user.type(screen.getByLabelText(/email/i), "user@example.com");
    await user.type(screen.getByLabelText(/password/i), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    await waitFor(() =>
      expect(screen.getByText("Dashboard placeholder")).toBeInTheDocument(),
    );
  });

  it("shows an error message on invalid credentials", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/auth/refresh")) return jsonResponse({ detail: "no" }, 401);
        if (url.includes("/auth/login")) {
          return jsonResponse({ detail: "Invalid email or password." }, 401);
        }
        return jsonResponse({ detail: "not mocked" }, 404);
      }),
    );

    renderLoginPage();
    await waitFor(() => screen.getByLabelText(/email/i));

    await user.type(screen.getByLabelText(/email/i), "user@example.com");
    await user.type(screen.getByLabelText(/password/i), "wrong-password");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    await waitFor(() =>
      expect(screen.getByText(/invalid email or password/i)).toBeInTheDocument(),
    );
  });
});
