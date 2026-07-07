// Auth is feature-flagged OFF by default so the demo stays frictionless
// (mirrors the backend's AUTH_ENABLED flag). Flip NEXT_PUBLIC_AUTH_ENABLED=1
// and every API call carries the JWT; sessions live in sessionStorage and
// die with the tab — nothing persistent on demo machines.

const TOKEN_KEY = "anvil-jwt";

export function isAuthEnabled(): boolean {
  return process.env.NEXT_PUBLIC_AUTH_ENABLED === "1";
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.sessionStorage.removeItem(TOKEN_KEY);
}

export function authHeaders(): Record<string, string> {
  const token = getToken();
  return isAuthEnabled() && token ? { Authorization: `Bearer ${token}` } : {};
}
