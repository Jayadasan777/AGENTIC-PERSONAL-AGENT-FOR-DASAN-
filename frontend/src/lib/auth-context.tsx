"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { authApi, tokenStore, type UserPublicResponse } from "@/lib/api";

interface AuthState {
  user: UserPublicResponse | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserPublicResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On mount, try to restore session using refresh token from sessionStorage
  useEffect(() => {
    const restore = async () => {
      const rt = tokenStore.getRefreshToken();
      if (!rt) {
        setIsLoading(false);
        return;
      }
      try {
        const tokens = await authApi.refresh(rt);
        tokenStore.setTokens(tokens.access_token, tokens.refresh_token);
        const me = await authApi.me();
        setUser(me);
      } catch {
        tokenStore.clear();
      } finally {
        setIsLoading(false);
      }
    };
    restore();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await authApi.login(email, password);
    tokenStore.setTokens(tokens.access_token, tokens.refresh_token);
    const me = await authApi.me();
    setUser(me);
  }, []);

  const register = useCallback(
    async (email: string, password: string, fullName?: string) => {
      await authApi.register({ email, password, full_name: fullName });
      await login(email, password);
    },
    [login]
  );

  const logout = useCallback(async () => {
    const rt = tokenStore.getRefreshToken();
    if (rt) {
      try {
        await authApi.logout(rt);
      } catch {
        // Proceed with logout even if server call fails
      }
    }
    tokenStore.clear();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, isLoading, isAuthenticated: !!user, login, register, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
