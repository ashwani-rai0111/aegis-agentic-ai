const TOKEN_KEY = "aegis_session_token";
const USER_KEY = "aegis_session_user";

export function getSessionToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(TOKEN_KEY);
}

export function getSessionUser(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(USER_KEY);
}

export function setSession(token: string, username: string) {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(USER_KEY, username);
}

export function clearSession() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
}

export function isLoggedIn(): boolean {
  return Boolean(getSessionToken());
}
