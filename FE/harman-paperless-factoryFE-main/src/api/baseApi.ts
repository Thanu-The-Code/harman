import { createApi, type BaseQueryFn } from "@reduxjs/toolkit/query/react";
import axios, { type AxiosRequestConfig } from "axios";
import { axiosInstance } from "../helpers";
import { getApiErrorMessage, type ApiError } from "./errors";

export interface ApiRequest {
  url: string;
  method?: AxiosRequestConfig["method"];
  data?: unknown;
  params?: Record<string, unknown>;
}

// FastAPI turns `?date_from=` into a 422, so empty filters are left out.
const cleanParams = (params?: Record<string, unknown>) =>
  params &&
  Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ""),
  );

const axiosBaseQuery: BaseQueryFn<ApiRequest, unknown, ApiError> = async ({
  url,
  method = "GET",
  data,
  params,
}) => {
  try {
    const result = await axiosInstance.request({ url, method, data, params: cleanParams(params) });
    return { data: result.data };
  } catch (error) {
    return {
      error: {
        status: axios.isAxiosError(error) ? error.response?.status : undefined,
        data: axios.isAxiosError(error) ? error.response?.data : undefined,
        message: getApiErrorMessage(error),
      },
    };
  }
};

/**
 * One API slice for the whole app. Each domain adds its endpoints with
 * `api.injectEndpoints` in its own `*.api.ts` file; every mutation invalidates
 * the tags it affects so lists, counts and badges refresh together.
 */
export const api = createApi({
  reducerPath: "api",
  baseQuery: axiosBaseQuery,
  tagTypes: [
    "Me",
    "Format",
    "Record",
    "Workflow",
    "MyApprovals",
    "Notifications",
    "Repository",
    "DCR",
    "RCR",
    "Users",
    "Roles",
    "Teams",
    "Departments",
    "Audit",
    "Stats",
  ],
  endpoints: () => ({}),
});
