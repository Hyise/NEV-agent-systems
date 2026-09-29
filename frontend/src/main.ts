import { createApp } from "vue";
import { createWebHashHistory } from "vue-router";
import App from "./App.vue";
import { createPlatformRouter } from "./router";
import "./style.css";

const router = createPlatformRouter(createWebHashHistory(), {
  home: () => import("./platform/PlatformHome.vue"),
  mcdm: () => import("./modules/mcdm/McdmWorkbench.vue"),
  adaptive: () => import("./platform/AdaptiveIntroduction.vue"),
});

createApp(App).use(router).mount("#app");
