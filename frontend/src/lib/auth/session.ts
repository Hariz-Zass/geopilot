const ACCESS_TOKEN_KEY = "geopilot_access_token";

export function getSessionAccessToken(storage: Pick<Storage, "getItem"> = window.sessionStorage): string | null {
  const value = storage.getItem(ACCESS_TOKEN_KEY)?.trim();
  return value || null;
}

export function setSessionAccessToken(token: string, storage: Pick<Storage, "setItem"> = window.sessionStorage): void {
  const value = token.trim();
  if (!value) throw new Error("access token must not be blank");
  storage.setItem(ACCESS_TOKEN_KEY, value);
}

export function clearSessionAccessToken(storage: Pick<Storage, "removeItem"> = window.sessionStorage): void {
  storage.removeItem(ACCESS_TOKEN_KEY);
}
