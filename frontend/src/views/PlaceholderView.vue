<script setup lang="ts">
import { computed } from "vue";
import { NCard, NTag } from "naive-ui";
import { useRoute } from "vue-router";

const route = useRoute();
const title = computed(() => String(route.meta.title ?? "页面"));
const icon = computed(() => String(route.meta.icon ?? "dashboard"));
const description = computed(() => String(route.meta.description ?? "新前端页面入口。"));
</script>

<template>
  <section class="placeholder-view">
    <NCard :bordered="false" class="placeholder-card">
      <div class="placeholder-body">
        <div class="placeholder-mark" aria-hidden="true">
          <morph-icon :icon="icon" size="32" stroke-width="1.8" />
        </div>
        <div class="placeholder-copy">
          <NTag type="info" round>Phase 5–8 基础架构</NTag>
          <h2>{{ title }}</h2>
          <p>{{ description }}</p>
          <p class="placeholder-note">当前仅验证 Router、Layout、导航与基础 API 接入；业务内容仍由 static/ 旧前端提供。</p>
          <div class="placeholder-status">
            <span class="status-ok">●</span>
              <span>Vue Router / API Layer ready</span>
              <span class="separator" />
              <span>ECharts 按页面加载</span>
            </div>
        </div>
      </div>
    </NCard>
  </section>
</template>
