<script setup lang="ts">
import { ref } from "vue";
import { NButton, NCard, NInput, useMessage } from "naive-ui";

const props = defineProps<{
  error: string;
  loading: boolean;
  login: (password: string) => Promise<boolean>;
}>();

const password = ref("");
const message = useMessage();
const logoSrc = "/assets/logo.svg";

async function submit(): Promise<void> {
  const success = await props.login(password.value);
  if (success) {
    password.value = "";
    message.success("登录成功");
  }
}
</script>

<template>
  <main class="login-page">
    <NCard :bordered="false" class="login-card">
      <div class="login-brand">
        <img :src="logoSrc" alt="" />
        <h1>oPanel</h1>
        <p>Macaron Edition · 管理员登录</p>
      </div>
      <form class="login-form" @submit.prevent="submit">
        <label for="password">管理员密码</label>
        <NInput
          id="password"
          v-model:value="password"
          type="password"
          show-password-on="click"
          autocomplete="current-password"
          autofocus
          placeholder="请输入管理员密码"
        />
        <p v-if="props.error" class="login-error" role="alert">{{ props.error }}</p>
        <NButton type="primary" attr-type="submit" :loading="props.loading" :disabled="!password.trim()" block>
          登录
        </NButton>
      </form>
    </NCard>
  </main>
</template>
