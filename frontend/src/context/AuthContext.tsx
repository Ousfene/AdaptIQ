import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { API_BASE } from '../config';

interface AuthUser {
  id: string;
  email: string;
  username: string;
  points: number;
  level: string;
  is_active: boolean;
  is_admin: boolean;
  created_at?: string;
}

interface AuthContextType {
  user: AuthUser | null;
  isLoading: boolean;
  login: (token: string, user: AuthUser) => void;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function isTokenExpired(token: string): boolean {
  try {
    const parts = token.split('.');
    if (parts.length < 2) {
      return true;
    }
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = payload.padEnd(payload.length + ((4 - (payload.length % 4)) % 4), '=');
    const decoded = atob(padded);
    const parsed = JSON.parse(decoded) as { exp?: number };
    if (!parsed.exp) {
      return false;
    }
    return Date.now() >= parsed.exp * 1000;
  } catch {
    return true;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const didBootstrapRef = useRef(false);
  const refreshInFlightRef = useRef(false);

  const login = (token: string, userData: AuthUser) => {
    localStorage.setItem('adaptiq_token', token);
    localStorage.setItem('adaptiq_user_id', userData.id);
    localStorage.removeItem('user_id');
    localStorage.setItem('adaptiq_user', JSON.stringify(userData));
    setUser(userData);
  };

  const logout = () => {
    localStorage.removeItem('adaptiq_token');
    localStorage.removeItem('adaptiq_user_id');
    localStorage.removeItem('user_id');
    localStorage.removeItem('adaptiq_user');
    sessionStorage.removeItem('adaptiq_classic_session_id');
    sessionStorage.removeItem('adaptiq_session_id');
    setUser(null);
  };

  const refreshUser = async () => {
    if (refreshInFlightRef.current) {
      return;
    }

    const token = localStorage.getItem('adaptiq_token');
    if (!token) {
      setUser(null);
      return;
    }

    if (isTokenExpired(token)) {
      logout();
      return;
    }

    refreshInFlightRef.current = true;
    try {
      const res = await fetch(`${API_BASE}/api/auth/me`, {
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
      });

      if (!res.ok) {
        logout();
        return;
      }

      const data = await res.json().catch(() => ({}));
      if (data?.user) {
        setUser(data.user as AuthUser);
        localStorage.setItem('adaptiq_user', JSON.stringify(data.user));
      }
    } catch {
      logout();
    } finally {
      refreshInFlightRef.current = false;
    }
  };

  useEffect(() => {
    if (didBootstrapRef.current) {
      return;
    }
    didBootstrapRef.current = true;

    const bootstrap = async () => {
      try {
        const cachedUser = localStorage.getItem('adaptiq_user');
        if (cachedUser) {
          setUser(JSON.parse(cachedUser));
        }
        await refreshUser();
      } finally {
        setIsLoading(false);
      }
    };
    bootstrap();
  }, []);

  const value = useMemo(
    () => ({ user, isLoading, login, logout, refreshUser }),
    [user, isLoading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
