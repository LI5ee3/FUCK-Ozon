import { createApp } from "vue";
import App from "./App.vue";
import router from "./app/router";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/layout.css";
import "./styles/components.css";

createApp(App).use(router).mount("#app");
