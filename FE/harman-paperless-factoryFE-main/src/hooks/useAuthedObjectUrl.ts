import { useEffect, useState } from "react";
import { axiosInstance } from "../helpers";
import { getApiErrorMessage } from "../api/errors";

interface AuthedFile {
  url: string | null; // object URL for <iframe>/<img>/<a download>
  mimeType: string | null;
  fileName: string | null;
  loading: boolean;
  error: string | null;
}

const fileNameFrom = (disposition?: string) => {
  const match = disposition?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  return match ? decodeURIComponent(match[1]) : null;
};

/**
 * File endpoints need the bearer token, which an <iframe src> cannot send, so
 * the file is fetched through axios and handed over as an object URL.
 * Pass `null` to load nothing.
 */
export const useAuthedObjectUrl = (apiPath: string | null | undefined): AuthedFile => {
  const [state, setState] = useState<AuthedFile>({
    url: null,
    mimeType: null,
    fileName: null,
    loading: false,
    error: null,
  });

  useEffect(() => {
    if (!apiPath) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState((s) => ({ ...s, loading: true, error: null }));

    axiosInstance
      .get<Blob>(apiPath.replace(/^\//, ""), { responseType: "blob" })
      .then((res) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data);
        setState({
          url: objectUrl,
          mimeType: res.data.type || null,
          fileName: fileNameFrom(res.headers["content-disposition"]),
          loading: false,
          error: null,
        });
      })
      .catch((error) => {
        if (!cancelled) {
          setState({ url: null, mimeType: null, fileName: null, loading: false, error: getApiErrorMessage(error) });
        }
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [apiPath]);

  return apiPath ? state : { url: null, mimeType: null, fileName: null, loading: false, error: null };
};
