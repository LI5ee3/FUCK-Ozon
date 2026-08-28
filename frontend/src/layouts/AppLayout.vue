<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  NButton,
  NDropdown,
  NLayout,
  NLayoutContent,
  NLayoutHeader,
  NLayoutSider,
  NMenu,
  NSelect,
  useDialog,
  useLoadingBar,
  useNotification,
} from "naive-ui";
import { RouterView, useRoute, useRouter } from "vue-router";
import { logout as logoutRequest } from "../api/auth";
import { ApiError, getErrorMessage, LOGOUT_EVENT } from "../api/client";
import { useShop } from "../composables/useShop";
import { useTheme } from "../composables/useTheme";
import { menuOptions } from "../router/navigation";

const route = useRoute();
const router = useRouter();
const dialog = useDialog();
const loadingBar = useLoadingBar();
const notification = useNotification();
const { selectedShopId, options: shopOptions, load: loadShops, selectShop } = useShop();
const { isDark, toggle: toggleTheme } = useTheme();

const pageTitle = computed(() => String(route.meta.title ?? "oPanel"));
const pageIcon = computed(() => String(route.meta.icon ?? "dashboard"));
const collapsed = ref(false);
const loggingOut = ref(false);
const logoSrc = "/assets/logo.svg";
const userMenuOptions = [{ label: "退出", key: "logout" }];

function navigate(path: string): void {
  void router.push(path);
}

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
  if (window.matchMedia("(max-width: 800px)").matches) {
    collapsed.value = true;
  }
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
      bordered
      collapse-mode="width"
      v-model:collapsed="collapsed"
      :collapsed-width="0"
      :width="240"
      show-trigger="bar"
      class="opanel-sider"
    >
      <div class="opanel-brand">
        <img class="opanel-logo" :src="logoSrc" alt="oPanel" />
        <div class="opanel-brand-copy">
          <strong class="opanel-brand-name">oPanel</strong>
          <span class="opanel-brand-pill">Macaron</span>
        </div>
      </div>
      <NMenu
        :value="route.path"
        :options="menuOptions"
        :collapsed="collapsed"
        :indent="16"
        class="opanel-menu"
        @update:value="navigate"
      />
      <div class="opanel-sider-footer">
        <NButton
          quaternary
          circle
          size="small"
          class="opanel-theme-button"
          aria-label="切换主题"
          title="切换主题"
          @click="toggleTheme"
        >
          <template #icon>
            <morph-icon :icon="isDark ? 'moon' : 'sun'" size="16" stroke-width="1.8" />
          </template>
        </NButton>
        <NButton
          quaternary
          circle
          size="small"
          class="opanel-settings-button"
          aria-label="系统设置"
          title="系统设置"
          @click="navigate('/settings')"
        >
          <template #icon>
            <morph-icon icon="settings" size="16" stroke-width="1.8" />
          </template>
        </NButton>
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
          <NSelect
            v-if="route.name !== 'profit'"
            :value="selectedShopId"
            :options="shopOptions"
            class="opanel-shop-select"
            aria-label="当前店铺"
            @update:value="selectShop"
          />
          <NButton quaternary circle class="opanel-theme-button" aria-label="切换主题" @click="toggleTheme">
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
          <NDropdown :options="userMenuOptions" trigger="click" @select="handleUserMenu">
            <NButton quaternary class="opanel-user-button">
              <span class="opanel-user-avatar">管</span>
              <span>管理员</span>
              <morph-icon icon="chevronDown" size="14" stroke-width="1.8" />
            </NButton>
          </NDropdown>
        </div>
      </NLayoutHeader>
      <NLayoutContent class="opanel-content">
        <RouterView />
      </NLayoutContent>
    </NLayout>
  </NLayout>
</template>
