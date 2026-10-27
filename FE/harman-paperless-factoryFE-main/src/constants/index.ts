const apiBaseUrl = import.meta.env.VITE_API_URL || import.meta.env.VITE_BASE_URL;

export const base_url = import.meta.env.DEV ? "/" : apiBaseUrl;