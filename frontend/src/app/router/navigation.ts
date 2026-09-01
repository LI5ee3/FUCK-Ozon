import type { IconName } from "../../shared/icons/tabler";

export type ToneName = "azure" | "lavender" | "mint" | "peach" | "butter";

export interface NavigationItem {
  name: string;
  label: string;
  path: string;
  icon: IconName;
  description: string;
}

export interface NavigationGroup {
  label: string;
  tone: ToneName;
  items: NavigationItem[];
}

export const navigationGroups: NavigationGroup[] = [
  {
    label: "业务概览",
    tone: "azure",
    items: [
      { name: "overview", label: "总览", path: "/", icon: "dashboard", description: "总览业务指标的 Vue 页面入口。" },
      { name: "orders", label: "订单", path: "/orders", icon: "orders", description: "订单数据的 Vue 页面入口。" },
      { name: "analytics", label: "流量与搜索分析", path: "/analytics", icon: "search", description: "流量与搜索分析的 Vue 页面入口。" },
    ],
  },
  {
    label: "广告管理",
    tone: "butter",
    items: [
      { name: "advertising", label: "广告总览", path: "/ads", icon: "barChart", description: "广告总览的 Vue 页面入口。" },
      { name: "ad-campaigns", label: "广告活动", path: "/ads/campaigns", icon: "layers", description: "广告活动的 Vue 页面入口。" },
      { name: "ad-skus", label: "SKU 广告分析", path: "/ads/skus", icon: "tag", description: "SKU 广告分析的 Vue 页面入口。" },
    ],
  },
  {
    label: "履约与异常",
    tone: "peach",
    items: [
      { name: "timeliness", label: "发货与配送时效", path: "/timeliness", icon: "delivery", description: "发货与配送时效的 Vue 页面入口。" },
      { name: "risk", label: "订单取消分析", path: "/risk", icon: "risk", description: "订单取消分析的 Vue 页面入口。" },
      { name: "returns", label: "异常订单明细", path: "/returns", icon: "returns", description: "异常订单明细的 Vue 页面入口。" },
      { name: "alerts", label: "异常预警", path: "/alerts", icon: "alertTriangle", description: "异常预警的 Vue 页面入口。" },
      { name: "complaints", label: "异常订单投诉", path: "/complaints", icon: "messageSquareAlert", description: "异常订单投诉的 Vue 页面入口。" },
    ],
  },
  {
    label: "供应链与数据",
    tone: "mint",
    items: [
      { name: "inventory", label: "销量与备货建议", path: "/inventory", icon: "stock", description: "销量与备货建议的 Vue 页面入口。" },
      { name: "profit", label: "实际利润", path: "/profit", icon: "trendingUp", description: "历史订单实际利润与数据完整性。" },
      { name: "transfer", label: "数据导入/导出", path: "/transfer", icon: "transfer", description: "数据导入与导出的 Vue 页面入口。" },
      { name: "sync", label: "数据同步中心", path: "/sync", icon: "sync", description: "数据同步中心的 Vue 页面入口。" },
    ],
  },
  {
    label: "系统配置",
    tone: "lavender",
    items: [
      { name: "rules", label: "商品匹配规则", path: "/rules", icon: "rules", description: "商品匹配规则的 Vue 页面入口。" },
      { name: "push-subscriptions", label: "推送订阅管理", path: "/push-subscriptions", icon: "zap", description: "推送订阅管理的 Vue 页面入口。" },
      { name: "dingtalk", label: "钉钉机器人", path: "/dingtalk", icon: "dingtalk", description: "钉钉机器人的 Vue 页面入口。" },
    ],
  },
];

export const navigationItems = navigationGroups.flatMap((group) => group.items);
