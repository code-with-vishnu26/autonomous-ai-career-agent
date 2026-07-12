import { describe, expect, it, vi, beforeEach } from "vitest";
import { apiFetch, apiFetchJson, SESSION_EXPIRED_EVENT } from "./http";
import { getToken, setToken } from "./tokenStore";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

beforeEach(() => {
  setToken(null);
});

describe("apiFetch", () => {
  it("attaches the Authorization header when a token is set", async () => {
    setToken("my-token");
    const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse({}),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/applications");

    const [, init] = fetchMock.mock.calls[0];
    const headers = new Headers((init as RequestInit).headers);
    expect(headers.get("Authorization")).toBe("Bearer my-token");
  });

  it("sends no Authorization header when there is no token", async () => {
    const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse({}),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/applications");

    const [, init] = fetchMock.mock.calls[0];
    const headers = new Headers((init as RequestInit).headers);
    expect(headers.has("Authorization")).toBe(false);
  });

  it("retries once via /auth/refresh on a 401 and updates the token", async () => {
    setToken("expired-token");
    let callCount = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/auth/refresh") {
        return jsonResponse({
          access_token: "new-token",
          token_type: "bearer",
          user: { id: "u1", email: "a@b.com", display_name: null, role: "user", created_at: "x" },
        });
      }
      callCount += 1;
      if (callCount === 1) return jsonResponse({ detail: "expired" }, 401);
      return jsonResponse({ ok: true });
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await apiFetch("/api/applications");

    expect(response.status).toBe(200);
    expect(getToken()).toBe("new-token");
  });

  it("dispatches session-expired and clears the token when refresh also fails", async () => {
    setToken("expired-token");
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/auth/refresh") return jsonResponse({ detail: "expired" }, 401);
      return jsonResponse({ detail: "unauthorized" }, 401);
    });
    vi.stubGlobal("fetch", fetchMock);

    const listener = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, listener);

    await apiFetch("/api/applications");

    expect(listener).toHaveBeenCalledOnce();
    expect(getToken()).toBeNull();
    window.removeEventListener(SESSION_EXPIRED_EVENT, listener);
  });

  it("does not attempt a refresh loop on /auth/refresh or /auth/login themselves", async () => {
    const fetchMock = vi.fn(() => jsonResponse({ detail: "no" }, 401));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/auth/login");

    expect(fetchMock).toHaveBeenCalledOnce();
  });
});

describe("VITE_API_BASE_URL", () => {
  it("prefixes every request path when set at build time", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.invalid");
    vi.resetModules();
    const { apiFetch: apiFetchWithBase } = await import("./http");

    const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse({}),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiFetchWithBase("/api/applications");

    const [calledUrl] = fetchMock.mock.calls[0];
    expect(calledUrl).toBe("https://api.example.invalid/api/applications");
    vi.unstubAllEnvs();
    vi.resetModules();
  });
});

describe("apiFetchJson", () => {
  it("returns the parsed body on success", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ hello: "world" })));
    const result = await apiFetchJson<{ hello: string }>("/api/health");
    expect(result).toEqual({ hello: "world" });
  });

  it("throws with the server's detail message on failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => jsonResponse({ detail: "not found" }, 404)),
    );
    await expect(apiFetchJson("/api/nope")).rejects.toThrow("not found");
  });

  it("returns undefined for a 204 No Content response", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(null, { status: 204 }))));
    const result = await apiFetchJson("/auth/logout", { method: "POST" });
    expect(result).toBeUndefined();
  });
});
