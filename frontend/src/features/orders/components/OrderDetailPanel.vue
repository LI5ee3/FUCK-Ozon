<script setup lang="ts">
import MorphIcon from "../../../shared/components/MorphIcon.vue";
import type { Order } from "../types";
import { formatBeijingDateTime, formatHours, formatInteger, formatMoney } from "../../../shared/utils/format";

const props = defineProps<{
  order: Order;
  copyValue: (value: string) => void;
}>();

function durationHours(from: string | null, to: string | null): number | null {
  if (!from || !to) return null;
  const start = new Date(from).getTime();
  const end = new Date(to).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  return (end - start) / 3_600_000;
}

function isShippingStatus(status: string): boolean {
  return /运输|配送|发货|待取件|已签收/.test(status);
}

function milestoneClass(kind: "created" | "shipped" | "delivered"): string {
  const { order } = props;
  if (kind === "created") return "is-completed";
  if (kind === "shipped") {
    return order.shipped_at ? "is-completed" : isShippingStatus(order.status_raw) ? "is-active" : order.status_raw === "已取消" ? "is-cancelled" : "is-pending";
  }
  return order.delivered_at || order.status_raw === "已签收"
    ? "is-completed"
    : order.status_raw === "已取消"
      ? "is-cancelled"
      : "is-pending";
}

function shippedNote(): string {
  const { order } = props;
  const duration = durationHours(order.created_at, order.shipped_at);
  return duration !== null
    ? `发货耗时 ${formatHours(duration)}`
    : order.shipped_at
      ? "已发货"
      : order.status_raw === "已取消"
        ? "取消未发货"
        : "等待发运";
}

function deliveredNote(): string {
  const { order } = props;
  const duration = durationHours(order.shipped_at, order.delivered_at);
  return duration !== null
    ? `配送耗时 ${formatHours(duration)}`
    : order.delivered_at
      ? "已签收"
      : order.status_raw === "已取消"
        ? "订单已取消"
        : order.shipped_at
          ? "配送中"
          : "待发货";
}

function copy(value: string | null): void {
  if (value) props.copyValue(value);
}

function formatUnitPrice(value: number | null, currency: string | null): string {
  return value == null ? "单价暂无" : formatMoney(value, currency ?? "");
}
</script>

<template>
  <div class="orders-detail-panel">
    <div class="orders-time-grid">
      <div class="orders-milestone" :class="milestoneClass('created')">
        <div class="orders-milestone-head">
          <morph-icon icon="shoppingBag" size="14" stroke-width="2" />
          <span>创建时间</span>
        </div>
        <strong>{{ formatBeijingDateTime(order.created_at) }}</strong>
        <small>订单已生成</small>
      </div>
      <div class="orders-milestone" :class="milestoneClass('shipped')">
        <div class="orders-milestone-head">
          <morph-icon icon="truck" size="14" stroke-width="2" />
          <span>实际发货时间</span>
        </div>
        <strong>{{ formatBeijingDateTime(order.shipped_at) }}</strong>
        <small>{{ shippedNote() }}</small>
      </div>
      <div class="orders-milestone" :class="milestoneClass('delivered')">
        <div class="orders-milestone-head">
          <morph-icon icon="checkCircle" size="14" stroke-width="2" />
          <span>实际签收时间</span>
        </div>
        <strong>{{ formatBeijingDateTime(order.delivered_at) }}</strong>
        <small>{{ deliveredNote() }}</small>
      </div>
    </div>

    <div class="orders-detail-products">
      <div class="orders-detail-products-head">
        <span>商品明细（{{ formatInteger(order.sku_types) }} 种 SKU · 共 {{ formatInteger(order.pieces) }} 件）</span>
        <span>单价与小计</span>
      </div>
      <div v-for="(item, index) in order.items" :key="`${item.sku ?? 'item'}-${index}`" class="orders-detail-product">
        <div class="orders-product-info-col">
          <strong class="orders-detail-product-title">{{ item.product_name_raw || "商品信息暂无" }}</strong>
          <small v-if="item.product_name_original && item.product_name_raw !== item.product_name_original">
            原始名称：{{ item.product_name_original }}
          </small>
          <div class="orders-product-meta-chips">
            <span class="orders-meta-chip">SKU <button v-if="item.sku" type="button" class="orders-copy-value" title="点击复制 SKU" @click.stop="copy(item.sku)">{{ item.sku }}</button><b v-else>暂无</b></span>
            <span class="orders-meta-chip">货号 <button v-if="item.offer_id" type="button" class="orders-copy-value" title="点击复制货号" @click.stop="copy(item.offer_id)">{{ item.offer_id }}</button><b v-else>暂无</b></span>
          </div>
        </div>
        <div class="orders-product-qty-col">
          <span class="orders-product-qty">× {{ formatInteger(item.quantity) }}</span>
        </div>
        <div class="orders-product-price-col">
          <strong>{{ formatUnitPrice(item.unit_price, item.price_currency) }}</strong>
          <small v-if="item.unit_price != null && item.quantity > 1">
            小计 {{ formatMoney(item.unit_price * item.quantity, item.price_currency ?? "") }}
          </small>
        </div>
      </div>
      <div v-if="order.items.length === 0" class="orders-detail-empty">商品明细暂无</div>
    </div>

    <div class="orders-detail-foot">
      <div class="orders-foot-total">
        <span>订单合计：</span>
        <strong>{{ formatMoney(order.amount_original, order.amount_currency ?? "") }}</strong>
        <span>（共 {{ formatInteger(order.pieces) }} 件）</span>
      </div>
      <div v-if="order.cancel_reason_raw" class="orders-alert-box orders-alert-box--danger">
        <morph-icon icon="alertTriangle" size="14" stroke-width="2" />
        <span><strong>取消原因：</strong>{{ order.cancel_reason_raw }}</span>
      </div>
      <div v-if="order.data_anomaly" class="orders-alert-box orders-alert-box--warning">
        <morph-icon icon="alertOctagon" size="14" stroke-width="2" />
        <span><strong>数据异常：</strong>订单实际时效字段与状态不一致，请核对原始数据。</span>
      </div>
    </div>
  </div>
</template>
