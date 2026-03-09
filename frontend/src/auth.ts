/**
 * Simple API key management for Vhive Star-Office-UI.
 * Token is read from VITE_VHIVE_API_KEY env var or localStorage.
 */

const STORAGE_KEY = "vhive_api_key";

export function getToken(): string | null {
  // Env var takes precedence (for CI / docker builds)
  const envToken = import.meta.env.VITE_VHIVE_API_KEY;
  if (typeof envToken === "string" && envToken) return envToken;

  return localStorage.getItem(STORAGE_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(STORAGE_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(STORAGE_KEY);
}

export function hasToken(): boolean {
  return !!getToken();
}
