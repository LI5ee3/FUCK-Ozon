import type { IconName } from "../../shared/icons/tabler";

declare module "vue-router" {
  interface RouteMeta {
    title?: string;
    icon?: IconName;
    description?: string;
  }
}
