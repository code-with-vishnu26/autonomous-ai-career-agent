import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { authApi } from "@/services/authApi";
import { SESSION_EXPIRED_EVENT } from "@/services/http";
import { getToken, setToken } from "@/services/tokenStore";
import type { User } from "@/types/api";
import { AuthContext } from "./auth-context";

/**
 * Owns the authenticated session (Phase 56, ADR-0074). On mount, attempts
 * one silent `POST /auth/refresh` using whatever refresh cookie the
 * browser already holds -- this is what makes a page reload not force a
 * fresh login every time, without ever touching `localStorage`.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);
  //  Refresh tokens rotate on every use (ADR-0074): the token presented
  //  is revoked the instant a replacement is issued. React 18/19 Strict
  //  Mode deliberately double-invokes effects in development -- without
  //  this guard, the two invocations would race each other's rotation,
  //  the second landing on an already-revoked cookie and losing the
  //  session it just restored. A ref (not state) so both invocations
  //  share the *same* in-flight promise instead of each starting a
  //  fresh request.
  const initialRefresh = useRef<Promise<void> | null>(null);

  useEffect(() => {
    const onExpired = () => {
      setUser(null);
      setSessionExpired(true);
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!initialRefresh.current) {
      initialRefresh.current = (async () => {
        try {
          const response = await fetch("/auth/refresh", {
            method: "POST",
            credentials: "include",
          });
          if (response.ok) {
            const body = await response.json();
            setToken(body.access_token);
            setUser(body.user);
          }
        } catch {
          // No session to resume -- stay logged out, no error to surface.
        }
      })();
    }
    initialRefresh.current.finally(() => {
      if (!cancelled) setIsLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await authApi.login(email, password);
    setToken(result.access_token);
    setUser(result.user);
    setSessionExpired(false);
  }, []);

  const register = useCallback(
    async (email: string, password: string, displayName?: string) => {
      const result = await authApi.register(email, password, displayName);
      setToken(result.access_token);
      setUser(result.user);
      setSessionExpired(false);
    },
    [],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setToken(null);
      setUser(null);
    }
  }, []);

  const dismissSessionExpired = useCallback(() => setSessionExpired(false), []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: user !== null && getToken() !== null,
        sessionExpired,
        login,
        register,
        logout,
        dismissSessionExpired,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
