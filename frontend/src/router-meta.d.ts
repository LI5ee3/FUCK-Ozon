import type { IconName } from "./icons/tabler";

declare module "vue-router" {
  interface RouteMeta {
    title?: string;
    icon?: IconName;
    description?: string;
  }
}
