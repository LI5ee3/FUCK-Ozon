import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import AppLayout from "../layouts/AppLayout.vue";
import PlaceholderView from "../views/PlaceholderView.vue";
import { navigationItems } from "./navigation";

const migratedViews: Partial<Record<string, RouteRecordRaw["component"]>> = {
  overview: () => import("../views/DashboardView.vue"),
  orders: () => import("../views/OrdersView.vue"),
  inventory: () => import("../views/InventoryView.vue"),
  analytics: () => import("../views/AnalyticsView.vue"),
  timeliness: () => import("../views/TimelinessView.vue"),
  risk: () => import("../views/RiskView.vue"),
  returns: () => import("../views/ReturnsView.vue"),
  alerts: () => import("../views/AlertsView.vue"),
  complaints: () => import("../views/ComplaintsView.vue"),
  advertising: () => import("../views/AdsView.vue"),
  "ad-campaigns": () => import("../views/AdCampaignsView.vue"),
  "ad-skus": () => import("../views/AdSkusView.vue"),
  profit: () => import("../views/ProfitView.vue"),
  transfer: () => import("../views/TransferView.vue"),
  sync: () => import("../views/SyncView.vue"),
  rules: () => import("../views/RulesView.vue"),
  "push-subscriptions": () => import("../views/PushSubscriptionsView.vue"),
};

const pageRoutes: RouteRecordRaw[] = navigationItems.map((item) => ({
  path: item.path === "/" ? "" : item.path.slice(1),
  name: item.name,
  component: migratedViews[item.name] ?? PlaceholderView,
  meta: { title: item.label, icon: item.icon, description: item.description },
}));

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    component: AppLayout,
    children: [
      ...pageRoutes,
      {
        path: "settings",
        name: "settings",
        component: PlaceholderView,
        meta: {
          title: "系统设置",
          icon: "settings",
          description: "系统设置的 Vue 页面入口。",
        },
      },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

export default createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
});
