import { StrictMode } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "./AuthContext";
import { useAuth } from "@/hooks/useAuth";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

function Probe() {
  const { isLoading, isAuthenticated, user } = useAuth();
  if (isLoading) return <div>loading</div>;
  return (
    <div>
      {isAuthenticated ? `authenticated as ${user?.email}` : "not authenticated"}
    </div>
  );
}

describe("AuthProvider under React StrictMode", () => {
  it("issues exactly one /auth/refresh call despite the double-invoked effect", async () => {
    const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) =>
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
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <StrictMode>
        <MemoryRouter>
          <AuthProvider>
            <Probe />
          </AuthProvider>
        </MemoryRouter>
      </StrictMode>,
    );

    await waitFor(() =>
      expect(screen.getByText("authenticated as user@example.com")).toBeInTheDocument(),
    );

    const refreshCalls = fetchMock.mock.calls.filter(
      (call) => String(call[0]) === "/auth/refresh",
    );
    expect(refreshCalls).toHaveLength(1);
  });
});
