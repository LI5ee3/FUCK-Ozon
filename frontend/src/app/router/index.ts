import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import AppLayout from "../layouts/AppLayout.vue";
import { navigationItems } from "./navigation";

const migratedViews: Partial<Record<string, RouteRecordRaw["component"]>> = {
  overview: () => import("../../features/dashboard/DashboardView.vue"),
  orders: () => import("../../features/orders/OrdersView.vue"),
  inventory: () => import("../../features/inventory/InventoryView.vue"),
  analytics: () => import("../../features/analytics/AnalyticsView.vue"),
  timeliness: () => import("../../features/timeliness/TimelinessView.vue"),
  risk: () => import("../../features/risk/RiskView.vue"),
  returns: () => import("../../features/returns/ReturnsView.vue"),
  alerts: () => import("../../features/alerts/AlertsView.vue"),
  complaints: () => import("../../features/complaints/ComplaintsView.vue"),
  advertising: () => import("../../features/advertising/AdsView.vue"),
  "ad-campaigns": () => import("../../features/advertising/AdCampaignsView.vue"),
  "ad-skus": () => import("../../features/advertising/AdSkusView.vue"),
  profit: () => import("../../features/profit/ProfitView.vue"),
  transfer: () => import("../../features/transfer/TransferView.vue"),
  sync: () => import("../../features/sync/SyncView.vue"),
  rules: () => import("../../features/rules/RulesView.vue"),
  "push-subscriptions": () => import("../../features/push-subscriptions/PushSubscriptionsView.vue"),
  dingtalk: () => import("../../features/dingtalk/DingTalkView.vue"),
};

function componentFor(name: string): NonNullable<RouteRecordRaw["component"]> {
  const component = migratedViews[name];
  if (!component) throw new Error(`Missing migrated Vue view: ${name}`);
  return component;
}

const pageRoutes: RouteRecordRaw[] = navigationItems.map((item) => ({
  path: item.path === "/" ? "" : item.path.slice(1),
  name: item.name,
  component: componentFor(item.name),
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
        component: () => import("../../features/settings/SettingsView.vue"),
        meta: {
          title: "系统设置",
          icon: "settings",
          description: "系统设置的 Vue 页面入口。",
        },
      },
      {
        path: "sku/:sku",
        name: "sku-detail",
        component: () => import("../../features/sku-detail/SkuDetailView.vue"),
        meta: { title: "SKU 360°", icon: "tag", description: "单店铺 SKU 的统一经营详情。" },
      },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

export default createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
});
