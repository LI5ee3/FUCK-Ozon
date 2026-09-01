<script setup lang="ts">
import { computed, onMounted } from "vue";
import {
  darkTheme,
  NConfigProvider,
  NDialogProvider,
  NLoadingBarProvider,
  NMessageProvider,
  NNotificationProvider,
  NSpin,
} from "naive-ui";
import { RouterView } from "vue-router";
import LoginView from "./app/auth/LoginView.vue";
import { useAuth } from "./app/auth/useAuth";
import { useTheme } from "./shared/composables/useTheme";
import { darkThemeOverrides, lightThemeOverrides } from "./theme/naive-theme";

const { authenticated, error, loading, login, ready, restoreSession } = useAuth();
const { isDark, init: initTheme } = useTheme();
const naiveTheme = computed(() => (isDark.value ? darkTheme : undefined));
const themeOverrides = computed(() => (isDark.value ? darkThemeOverrides : lightThemeOverrides));

onMounted(() => {
  initTheme();
  void restoreSession();
});
</script>

<template>
  <NConfigProvider :theme="naiveTheme" :theme-overrides="themeOverrides">
    <NMessageProvider>
      <NNotificationProvider>
        <NDialogProvider>
          <NLoadingBarProvider>
            <div v-if="!ready" class="app-loading">
              <NSpin size="medium" />
              <span>正在连接 O3Pilot…</span>
            </div>
            <LoginView
              v-else-if="!authenticated"
              :error="error"
              :loading="loading"
              :login="login"
            />
            <RouterView v-else />
          </NLoadingBarProvider>
        </NDialogProvider>
      </NNotificationProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>
