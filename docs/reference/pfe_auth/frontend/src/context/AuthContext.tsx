import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { API_BASE } from '../config';

interface User {
  id: string;
  email: string;
  username: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (username: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('adaptiq_token'));
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!token) { setIsLoading(false); return; }
    fetch(`${API_BASE}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => setUser(data))
      .catch(() => { localStorage.removeItem('adaptiq_token'); setToken(null); })
      .finally(() => setIsLoading(false));
  }, [token]);

  const login = async (email: string, password: string) => {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error("Login failed. Please check your email and password.");
    }
    const data = await res.json();

    // Validate response structure
    if (!data.access_token || typeof data.access_token !== 'string') {
      throw new Error('Invalid login response: missing or invalid access_token');
    }
    if (!data.user?.id || typeof data.user.id !== 'string') {
      throw new Error('Invalid login response: missing or invalid user.id');
    }

    localStorage.setItem('adaptiq_token', data.access_token);
    // Store real user ID for quiz session tracking
    localStorage.setItem('adaptiq_user_id', data.user.id);
    setToken(data.access_token);
    setUser(data.user);
  };

  const signup = async (username: string, email: string, password: string) => {
    const res = await fetch(`${API_BASE}/api/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error("Registration failed. Please try again.");
    }
    const data = await res.json();

    // Validate response structure
    if (!data.access_token || typeof data.access_token !== 'string') {
      throw new Error('Invalid signup response: missing or invalid access_token');
    }
    if (!data.user?.id || typeof data.user.id !== 'string') {
      throw new Error('Invalid signup response: missing or invalid user.id');
    }

    localStorage.setItem('adaptiq_token', data.access_token);
    localStorage.setItem('adaptiq_user_id', data.user.id);
    setToken(data.access_token);
    setUser(data.user);
  };

  const logout = () => {
    localStorage.removeItem('adaptiq_token');
    localStorage.removeItem('adaptiq_user_id');
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
};
