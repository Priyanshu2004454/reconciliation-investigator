"use client";

import { createContext, useContext, useEffect, useState, ReactNode, useCallback } from "react";
import { useRouter } from "next/navigation";
import * as api from "./api";
import type { MerchantAccount, User } from "./types";

interface AuthContextValue {
  user: User | null;
  merchantAccount: MerchantAccount | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => void;
  refreshMerchantAccount: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [merchantAccount, setMerchantAccount] = useState<MerchantAccount | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const refreshMerchantAccount = useCallback(async () => {
    try {
      const account = await api.getMyMerchantAccount();
      setMerchantAccount(account);
    } catch {
      setMerchantAccount(null);
    }
  }, []);

  useEffect(() => {
    const stored = typeof window !== "undefined" ? localStorage.getItem("ri_user") : null;
    const token = typeof window !== "undefined" ? localStorage.getItem("ri_token") : null;

    async function init() {
      if (stored && token) {
        setUser(JSON.parse(stored));
        await refreshMerchantAccount();
      }
      setLoading(false);
    }
    init();
  }, [refreshMerchantAccount]);

  const login = async (email: string, password: string) => {
    const res = await api.login(email, password);
    api.setToken(res.access_token);
    localStorage.setItem("ri_user", JSON.stringify(res.user));
    setUser(res.user);
    await refreshMerchantAccount();
    router.push("/dashboard");
  };

  const registerFn = async (email: string, password: string, fullName: string) => {
    const res = await api.register(email, password, fullName);
    api.setToken(res.access_token);
    localStorage.setItem("ri_user", JSON.stringify(res.user));
    setUser(res.user);
    router.push("/settings");
  };

  const logout = () => {
    api.setToken(null);
    localStorage.removeItem("ri_user");
    setUser(null);
    setMerchantAccount(null);
    router.push("/login");
  };

  return (
    <AuthContext.Provider
      value={{ user, merchantAccount, loading, login, register: registerFn, logout, refreshMerchantAccount }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
