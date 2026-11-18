import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import type { User } from "./types";

type AuthCtx = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
};

const Ctx = createContext<AuthCtx>(null as unknown as AuthCtx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!localStorage.getItem("if_token")) {
      setLoading(false);
      return;
    }
    api.get("/api/auth/me").then((r) => setUser(r.data)).catch(() => localStorage.removeItem("if_token")).finally(() => setLoading(false));
  }, []);

  const accept = (data: { token: string; user: User }) => {
    localStorage.setItem("if_token", data.token);
    setUser(data.user);
  };

  return (
    <Ctx.Provider
      value={{
        user,
        loading,
        login: async (email, password) => accept((await api.post("/api/auth/login", { email, password })).data),
        register: async (name, email, password) => accept((await api.post("/api/auth/register", { name, email, password })).data),
        logout: () => {
          localStorage.removeItem("if_token");
          setUser(null);
        },
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);
