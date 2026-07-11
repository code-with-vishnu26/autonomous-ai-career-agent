import type { ReactNode } from "react";
import { useTheme } from "@/hooks/useTheme";
import { ThemeContext } from "./theme-context";

/**
 * Applies dark/light mode at the app root, so it's in effect on every
 * route -- including the public auth pages (login/register/...), which
 * mount outside `AppLayout`/`Navbar` and would otherwise never see the
 * persisted theme applied (Phase 56 found this: dark mode only worked
 * once a Navbar had mounted at least once in the session).
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const value = useTheme();
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
