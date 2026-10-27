/** A retry for a failed load, unless retrying cannot help: the thing is gone (404) or not yours (403). */
export const retryUnlessFinal = (error: unknown, retry: () => void) => {
  const status = error && typeof error === "object" && "status" in error ? (error as { status?: number }).status : undefined;
  return status === 404 || status === 403 ? undefined : retry;
};
