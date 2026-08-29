import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

const apiTarget = process.env.OPANEL_API_TARGET ?? "http://127.0.0.1:38652";

export default defineConfig({
  plugins: [
    vue(),
  ],
  server: {
    proxy: {
      "/api": { target: apiTarget },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
