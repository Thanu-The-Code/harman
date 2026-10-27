import axios, { type InternalAxiosRequestConfig } from "axios";
import { base_url } from "../constants";
import { clearSession, getToken, LOGIN_PATH } from "../api/session";

const NO_TOKEN_URLS = ["api/auth/login", "api/auth/setup"];

/* ---------- instance ---------- */
export const axiosInstance = axios.create({
  baseURL: base_url,
  headers: { "Content-Type": "application/json" },
  // the backend's HttpOnly session cookie backs up the bearer token
  withCredentials: true,
  // FastAPI reads repeated keys (?status=a&status=b), not status[]=a
  paramsSerializer: { indexes: null },
});

axiosInstance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const skipToken = NO_TOKEN_URLS.some((u) => config.url?.includes(u));

  // let the browser set the multipart boundary for file uploads
  if (config.data instanceof FormData) {
    config.headers.delete("Content-Type");
  }

  const token = getToken();
  if (token && !skipToken && !config.headers.has("Authorization")) {
    config.headers.set("Authorization", `Bearer ${token}`);
  }

  return config;
});

let isLoggingOut = false;

axiosInstance.interceptors.response.use(
  (response) => response,
  (error) => {
    // only 401 means the session is invalid; 403 means "not allowed", so don't log out
    const isLoginRequest = error?.config?.url?.includes("api/auth/login");
    const onLoginPage = window.location.pathname === LOGIN_PATH;
    if (error?.response?.status === 401 && !isLoginRequest && !onLoginPage && !isLoggingOut) {
      isLoggingOut = true;
      clearSession();
      // a full reload also drops every cached API response; the login page says why
      // (a toast would not survive the reload) and brings the person back here afterwards
      const from = encodeURIComponent(`${window.location.pathname}${window.location.search}`);
      window.location.replace(`${window.location.origin}${LOGIN_PATH}?expired=1&from=${from}`);
    }

    return Promise.reject(error);
  },
);
