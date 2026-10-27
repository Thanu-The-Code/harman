import { toast } from "react-toastify";
import { axiosInstance } from "../helpers";
import { getApiErrorMessage } from "../api/errors";

/** Fetch an authenticated file (the API needs the bearer token) and open it in a new tab. */
export const openAuthedFile = async (apiPath: string) => {
  try {
    const res = await axiosInstance.get<Blob>(apiPath.replace(/^\//, ""), { responseType: "blob" });
    window.open(URL.createObjectURL(res.data), "_blank", "noopener");
  } catch (error) {
    toast.error(getApiErrorMessage(error, "Could not open the file."));
  }
};

/** Fetch an authenticated file and save it under `filename` (a download, not a new tab). */
export const downloadAuthedFile = async (apiPath: string, filename: string) => {
  try {
    const res = await axiosInstance.get<Blob>(apiPath.replace(/^\//, ""), { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    // kept until the download has started: some browsers drop the name of a link already gone
    setTimeout(() => {
      link.remove();
      URL.revokeObjectURL(url);
    }, 10_000);
  } catch (error) {
    toast.error(getApiErrorMessage(error, "Could not download the file."));
  }
};
