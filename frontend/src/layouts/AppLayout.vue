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
import { getErrorMessage } from "../api/client";
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
const logoSrc = "/static/logo.svg";
const userMenuOptions = [{ label: "退出", key: "logout" }];

function navigate(path: string): void {
  void router.push(path);
}

function showLogoutNotice(): void {
  dialog.info({
    title: "退出登录",
    content: "当前后端只提供登录与 Session 查询接口，尚未提供退出接口。",
    positiveText: "知道了",
  });
}

function handleUserMenu(key: string | number): void {
  if (key === "logout") showLogoutNotice();
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
        class="opanel-menu"
        @update:value="navigate"
      />
      <div class="opanel-sider-footer">
        <NButton quaternary circle size="small" class="opanel-theme-button" @click="toggleTheme">
          <template #icon>
            <morph-icon :icon="isDark ? 'moon' : 'sun'" size="16" stroke-width="1.8" />
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
