import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, clearTokens, storeTokens } from "@/lib/api-client";
import { ACCESS_TOKEN_STORAGE_KEY } from "@/lib/constants";
import type { TokenResponse, User } from "@/types";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadCurrentUser = useCallback(async () => {
    const token = localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
    if (!token) {
      setIsLoading(false);
      return;
    }
    try {
      const currentUser = await api.get<User>("/auth/me");
      setUser(currentUser);
    } catch {
      clearTokens();
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCurrentUser();
  }, [loadCurrentUser]);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await api.post<TokenResponse>("/auth/login", { email, password }, { skipAuth: true });
    storeTokens(tokens);
    const currentUser = await api.get<User>("/auth/me");
    setUser(currentUser);
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const tokens = await api.post<TokenResponse>("/auth/register", { email, password }, { skipAuth: true });
    storeTokens(tokens);
    const currentUser = await api.get<User>("/auth/me");
    setUser(currentUser);
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, isLoading, isAuthenticated: user !== null, login, register, logout }),
    [user, isLoading, login, register, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
