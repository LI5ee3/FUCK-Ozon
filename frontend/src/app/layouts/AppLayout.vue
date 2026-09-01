<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import {
  NButton,
  NDropdown,
  NLayout,
  NLayoutContent,
  NLayoutHeader,
  NLayoutSider,
  NSelect,
  useDialog,
  useLoadingBar,
  useNotification,
} from "naive-ui";
import { RouterView, useRoute, useRouter } from "vue-router";
import { logout as logoutRequest } from "../auth/api";
import { ApiError, getErrorMessage, LOGOUT_EVENT } from "../../shared/api/client";
import { useShop } from "../../shared/composables/useShop";
import { useTheme } from "../../shared/composables/useTheme";
import { navigationGroups } from "../router/navigation";

const route = useRoute();
const router = useRouter();
const dialog = useDialog();
const loadingBar = useLoadingBar();
const notification = useNotification();
const { selectedShopId, options: shopOptions, load: loadShops, selectShop } = useShop();
const { isDark, toggle: toggleTheme } = useTheme();

const pageTitle = computed(() => String(route.meta.title ?? "oPanel"));
const pageIcon = computed(() => route.meta.icon ?? "dashboard");
const collapsed = ref(false);
let navigationMedia: MediaQueryList | undefined;
function syncNavigation(event: MediaQueryListEvent): void {
  collapsed.value = event.matches;
}
const loggingOut = ref(false);
const logoSrc = "/assets/logo.svg";
const userMenuOptions = [{ label: "退出", key: "logout" }];

function navigate(path: string): void {
  void router.push(path);
}

/* Click pulse: the item's icon spring-morphs to a check, then reverts. */
const morphingPath = ref<string | null>(null);
let morphTimer: ReturnType<typeof setTimeout> | undefined;

function pulseNavIcon(path: string): void {
  morphingPath.value = path;
  clearTimeout(morphTimer);
  morphTimer = setTimeout(() => {
    morphingPath.value = null;
  }, 700);
}

onBeforeUnmount(() => {
  clearTimeout(morphTimer);
  navigationMedia?.removeEventListener("change", syncNavigation);
});

function showLogoutDialog(): void {
  let dialogInstance: ReturnType<typeof dialog.warning> | undefined;
  dialogInstance = dialog.warning({
    title: "退出登录",
    content: "确定要退出当前登录吗？",
    positiveText: "退出",
    negativeText: "取消",
    onPositiveClick: async () => {
      if (loggingOut.value) return false;
      loggingOut.value = true;
      if (dialogInstance) dialogInstance.loading = true;
      try {
        await logoutRequest();
        window.dispatchEvent(new Event(LOGOUT_EVENT));
        return true;
      } catch (cause) {
        if (!(cause instanceof ApiError) || cause.status !== 401) {
          notification.error({
            title: "退出登录失败",
            content: getErrorMessage(cause),
            duration: 4500,
          });
        }
        return false;
      } finally {
        loggingOut.value = false;
        if (dialogInstance) dialogInstance.loading = false;
      }
    },
  });
}

function handleUserMenu(key: string | number): void {
  if (key === "logout") showLogoutDialog();
}

onMounted(async () => {
  navigationMedia = window.matchMedia("(max-width: 800px)");
  collapsed.value = navigationMedia.matches;
  navigationMedia.addEventListener("change", syncNavigation);
  loadingBar.start();
  try {
    await loadShops();
  } catch (cause) {
    notification.error({
      title: "店铺信息加载失败",
      content: getErrorMessage(cause),
      duration: 4500,
    });
  } finally {
    loadingBar.finish();
  }
});
</script>

<template>
  <NLayout has-sider class="opanel-shell">
    <NLayoutSider
      id="opanel-navigation"
      bordered
      collapse-mode="width"
      v-model:collapsed="collapsed"
      :collapsed-width="0"
      :width="240"
      class="opanel-sider"
    >
      <div class="opanel-brand">
        <img class="opanel-logo" :src="logoSrc" alt="oPanel" />
        <div class="opanel-brand-copy">
          <strong class="opanel-brand-name">oPanel</strong>
          <span class="opanel-brand-pill tone-butter">Macaron</span>
        </div>
      </div>
      <nav class="opanel-nav" aria-label="主导航">
        <section
          v-for="group in navigationGroups"
          :key="group.label"
          class="opanel-nav-group"
          :data-tone="group.tone"
        >
          <p class="opanel-nav-group-title">{{ group.label }}</p>
          <RouterLink
            v-for="item in group.items"
            :key="item.path"
            :to="item.path"
            class="opanel-nav-item"
            :class="{
              'opanel-nav-item--selected': route.path === item.path,
              [`tone-${group.tone}`]: route.path === item.path,
            }"
            :aria-current="route.path === item.path ? 'page' : undefined"
            @click="pulseNavIcon(item.path)"
          >
            <morph-icon
              :icon="morphingPath === item.path ? 'check' : item.icon"
              size="18"
              stroke-width="1.8"
            />
            <span>{{ item.label }}</span>
          </RouterLink>
        </section>
      </nav>
      <div class="opanel-sider-footer">
        <NDropdown :options="userMenuOptions" trigger="click" @select="handleUserMenu">
          <button type="button" class="opanel-user-card">
            <span class="opanel-user-avatar">管</span>
            <span>管理员</span>
            <morph-icon icon="chevronDown" size="14" stroke-width="1.8" />
          </button>
        </NDropdown>
      </div>
    </NLayoutSider>

    <NLayout>
      <NLayoutHeader bordered class="opanel-header">
        <div class="opanel-heading">
          <p class="opanel-eyebrow">OPANEL · MACARON EDITION</p>
          <h1>
            <morph-icon :icon="pageIcon" size="20" stroke-width="1.8" />
            {{ pageTitle }}
          </h1>
        </div>
        <div class="opanel-header-actions">
          <NButton
            quaternary
            circle
            :aria-label="collapsed ? '展开导航' : '收起导航'"
            :title="collapsed ? '展开导航' : '收起导航'"
            :aria-expanded="!collapsed"
            aria-controls="opanel-navigation"
            @click="collapsed = !collapsed"
          >
            <template #icon><morph-icon :icon="collapsed ? 'chevronRight' : 'chevronLeft'" size="17" stroke-width="1.8" /></template>
          </NButton>
          <NSelect
            :value="selectedShopId"
            :options="shopOptions"
            class="opanel-shop-select"
            aria-label="当前店铺"
            @update:value="selectShop"
          />
          <NButton quaternary circle class="opanel-theme-button" aria-label="切换主题" title="切换主题" @click="toggleTheme">
            <template #icon>
              <morph-icon :icon="isDark ? 'moon' : 'sun'" size="17" stroke-width="1.8" />
            </template>
          </NButton>
          <NButton
            quaternary
            circle
            class="opanel-settings-button"
            aria-label="系统设置"
            title="系统设置"
            @click="navigate('/settings')"
          >
            <template #icon>
              <morph-icon icon="settings" size="17" stroke-width="1.8" />
            </template>
          </NButton>
        </div>
      </NLayoutHeader>
      <NLayoutContent class="opanel-content">
        <RouterView />
      </NLayoutContent>
    </NLayout>
  </NLayout>
</template>
