import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiBaseUrl = env.VITE_API_URL || env.VITE_BASE_URL;

  if (!apiBaseUrl) {
    throw new Error("Set VITE_API_URL or VITE_BASE_URL to the API server URL.");
  }

  let apiTarget: string;
  try {
    apiTarget = new URL(apiBaseUrl).origin;
  } catch {
    throw new Error("VITE_API_URL or VITE_BASE_URL must be a valid absolute URL.");
  }

  return {
    plugins: [react()],
    // react-form-builder2 expects the webpack/Node `global` variable
    define: {
      global: "globalThis",
    },
    optimizeDeps: {
      // Vite 8 (rolldown)
      rolldownOptions: {
        transform: { define: { global: "globalThis" } },
      },
    },
    build: {
      // Routes are lazy-loaded (src/App.tsx). What remains above Vite's 500 kB
      // default are vendor chunks confined to their screens: the form designer
      // (react-form-builder2), the dashboard charts (ag-charts) and the grids
      // (ag-grid). The entry chunk is ~320 kB.
      chunkSizeWarningLimit: 1600,
    },
    server: {
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
          secure: true,
        },
      },
    },
  };
});