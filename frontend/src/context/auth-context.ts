import { createContext } from "react";
import type { User } from "@/types/api";

export interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  sessionExpired: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => Promise<void>;
  dismissSessionExpired: () => void;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);
