import { createContext } from "react";

export interface ThemeContextValue {
  theme: "light" | "dark";
  toggle: () => void;
}

export const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);
