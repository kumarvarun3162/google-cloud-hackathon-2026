import { createContext, useContext, useEffect, useState } from "react";

const TOKEN_KEY = "citizenpriority_token";
const AuthContext = createContext(null);

// Mock credentials for testing. Once the FastAPI backend exposes a real
// /api/auth/login, replace the body of login() with a fetch() that
// returns a real JWT — the rest of the app only cares that login()
// resolves/rejects and that a token ends up in localStorage.
const DEMO_EMAIL = "mp@citizenpriority.gov";
const DEMO_PASSWORD = "demo1234";

function decodeMockPayload(token) {
  try {
    return JSON.parse(atob(token.split(".")[1]));
  } catch {
    return null;
  }
}

function makeMockToken(email) {
  const header = btoa(JSON.stringify({ alg: "mock", typ: "JWT" }));
  const payload = btoa(
    JSON.stringify({ sub: email, exp: Date.now() + 1000 * 60 * 60 * 8 }),
  );
  return `${header}.${payload}.mocksignature`;
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));

  useEffect(() => {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  }, [token]);

  async function login(email, password) {
    await new Promise((resolve) => setTimeout(resolve, 600));
    if (email !== DEMO_EMAIL || password !== DEMO_PASSWORD) {
      throw new Error("invalid_credentials");
    }
    setToken(makeMockToken(email));
  }

  function logout() {
    setToken(null);
  }

  const payload = token ? decodeMockPayload(token) : null;
  const isExpired = payload ? payload.exp < Date.now() : true;
  const isAuthenticated = Boolean(token) && !isExpired;

  return (
    <AuthContext.Provider
      value={{ isAuthenticated, user: payload?.sub, login, logout }}
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
