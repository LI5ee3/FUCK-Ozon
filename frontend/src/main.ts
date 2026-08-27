import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import "./style.css";

function loadLegacyIcons(): Promise<void> {
  return new Promise((resolve) => {
    const script = document.createElement("script");
    script.src = "/static/morphicons.js";
    script.onload = () => resolve();
    script.onerror = () => resolve();
    document.head.append(script);
  });
}

void loadLegacyIcons().then(() => {
  createApp(App).use(router).mount("#app");
});
