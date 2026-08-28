import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const apiTarget = process.env.OPANEL_API_TARGET ?? "http://127.0.0.1:38652";

export default defineConfig({
  plugins: [
    vue({
      template: {
        compilerOptions: {
          isCustomElement: (tag) => tag === "morph-icon",
        },
      },
    }),
  ],
  server: {
    proxy: {
      "/api": { target: apiTarget },
    },
  },
});
