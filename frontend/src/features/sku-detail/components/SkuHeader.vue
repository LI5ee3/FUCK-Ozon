<script setup lang="ts">
import { NButton } from "naive-ui";
import MorphIcon from "../../../shared/components/MorphIcon.vue";
import { formatBeijingDateTime } from "../../../shared/utils/format";
import type { SkuFreshness, SkuIdentity } from "../types";

defineProps<{ identity: SkuIdentity; freshness: SkuFreshness }>();
defineEmits<{ back: [] }>();
</script>

<template>
  <header class="sku-detail-header">
    <div class="sku-detail-header-top">
      <NButton quaternary size="small" @click="$emit('back')">
        <template #icon><MorphIcon icon="chevronLeft" size="16" stroke-width="2" /></template>
        返回
      </NButton>
      <span class="sku-detail-eyebrow">SKU 360° · 经营详情</span>
    </div>
    <div class="sku-detail-title-row">
      <div class="sku-detail-title-copy">
        <h1>{{ identity.display_name }}</h1>
        <p v-if="identity.product_name_raw && identity.product_name_raw !== identity.display_name">
          原始商品名：{{ identity.product_name_raw }}
        </p>
      </div>
      <span class="sku-detail-shop-badge">{{ identity.shop_name }}</span>
    </div>
    <div class="sku-detail-identity-grid">
      <span><small>SKU</small><b>{{ identity.sku }}</b></span>
      <span><small>Offer ID</small><b>{{ identity.offer_id || "—" }}</b></span>
      <span><small>主 Offer</small><b>{{ identity.primary_offer_id || "—" }}</b></span>
      <span><small>商品组</small><b>{{ identity.group_id ?? "未分组" }}</b></span>
    </div>
    <div class="sku-detail-freshness" aria-label="各数据模块更新时间">
      <span>订单 {{ formatBeijingDateTime(freshness.orders) }}</span>
      <span>库存 {{ formatBeijingDateTime(freshness.inventory) }}</span>
      <span>广告 {{ formatBeijingDateTime(freshness.advertising) }}</span>
    </div>
  </header>
</template>
