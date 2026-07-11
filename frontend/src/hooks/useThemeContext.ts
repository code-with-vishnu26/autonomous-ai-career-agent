import { useContext } from "react";
import { ThemeContext, type ThemeContextValue } from "@/context/theme-context";

export function useThemeContext(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useThemeContext must be used within a ThemeProvider");
  return context;
}
