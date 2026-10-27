// The signed-in session lives in localStorage so a reload keeps it. The
// backend also sets an HttpOnly session cookie; the bearer token is what the
// axios interceptor sends.
const TOKEN_KEY = "token";

export const LOGIN_PATH = "/login";

export const getToken = (): string | null => {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
};

export const setToken = (token: string) => {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* storage blocked: the session cookie still carries the sign-in */
  }
};

export const clearSession = () => {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem("loginDetails"); // written by the old login flow
  } catch {
    /* ignore */
  }
};
