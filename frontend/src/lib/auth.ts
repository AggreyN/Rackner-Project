// Client-side session helpers. The token is a JWT from POST /auth/login
// (bcrypt-hashed credentials server-side — Aggrey's lane); the frontend
// only stores and forwards it. sessionStorage keeps the demo simple and
// clears on tab close — no long-lived credentials in the browser.

const TOKEN_KEY = "fdi_token";
const EMAIL_KEY = "fdi_email";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(TOKEN_KEY);
}

export function getEmail(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(EMAIL_KEY);
}

export function setSession(token: string, email: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(EMAIL_KEY, email);
}

export function clearSession(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(EMAIL_KEY);
}

export function isSignedIn(): boolean {
  return getToken() !== null;
}
