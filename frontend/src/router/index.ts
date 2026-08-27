import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import AppLayout from "../layouts/AppLayout.vue";
import PlaceholderView from "../views/PlaceholderView.vue";
import { navigationItems } from "./navigation";

const pageRoutes: RouteRecordRaw[] = navigationItems.map((item) => ({
  path: item.path === "/" ? "" : item.path.slice(1),
  name: item.name,
  component: item.name === "overview"
    ? () => import("../views/DashboardView.vue")
    : item.name === "orders"
      ? () => import("../views/OrdersView.vue")
      : item.name === "inventory"
        ? () => import("../views/InventoryView.vue")
        : PlaceholderView,
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
