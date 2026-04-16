import { createContext, useContext, useState, useCallback, ReactNode } from "react";
import type { User } from "../types";

interface AuthState {
  token: string | null;
  user: User | null;
}

interface AuthContextValue extends AuthState {
  setAuth: (token: string, user: User) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = "geo_token";
const USER_KEY = "geo_user";

function loadFromStorage(): AuthState {
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    const raw = localStorage.getItem(USER_KEY);
    const user = raw ? (JSON.parse(raw) as User) : null;
    return { token, user };
  } catch {
    return { token: null, user: null };
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(loadFromStorage);

  const setAuth = useCallback((token: string, user: User) => {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    setState({ token, user });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setState({ token: null, user: null });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, setAuth, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
