import axios from "axios";

// The backend replaces FastAPI's `{detail}` with
// `{ error: { status_code, message, detail, validation_errors? } }`.
// The rate limiter answers with `{ detail, error: "rate_limit_exceeded" }`.
interface ApiErrorBody {
  error?:
    | string
    | {
        status_code?: number;
        message?: string;
        detail?: unknown;
        validation_errors?: { field?: string; message?: string }[];
      };
  detail?: unknown;
}

export interface ApiError {
  status?: number;
  data?: unknown;
  message: string;
}

const FALLBACK = "Something went wrong. Please try again.";

const detailText = (detail: unknown): string | undefined => {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  return undefined;
};

const messageFromBody = (body: unknown, status?: number): string | undefined => {
  if (status === 429) return "Too many requests. Please wait a moment and try again.";
  if (!body || typeof body !== "object") return undefined;
  const { error, detail } = body as ApiErrorBody;

  if (error && typeof error === "object") {
    const validation = error.validation_errors
      ?.map((v) => (v.field ? `${v.field.replace(/^body -> /, "")}: ${v.message}` : v.message))
      .filter(Boolean)
      .join("; ");
    return detailText(error.detail) || validation || error.message;
  }
  return detailText(detail);
};

const isApiError = (value: unknown): value is ApiError =>
  !!value && typeof value === "object" && "message" in value && !(value instanceof Error);

/** A readable message for any error thrown by the API layer. */
export const getApiErrorMessage = (error: unknown, fallback = FALLBACK): string => {
  if (axios.isAxiosError(error)) {
    if (!error.response) return "Cannot reach the server. Check your connection.";
    return messageFromBody(error.response.data, error.response.status) || fallback;
  }
  if (isApiError(error)) {
    // the base query stored the generic message; the caller's own fallback says more
    const stored = error.message && error.message !== FALLBACK ? error.message : undefined;
    return messageFromBody(error.data, error.status) || stored || fallback;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
};
