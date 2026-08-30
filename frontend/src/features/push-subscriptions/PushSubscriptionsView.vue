<script setup lang="ts">
import "../../styles/analytics.css";
import "./push-subscriptions.css";
import { onBeforeUnmount, onMounted, reactive } from "vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import {
  NAlert,
  NButton,
  NCard,
  NCheckbox,
  NInput,
  NSkeleton,
  NSwitch,
  NTag,
  useDialog,
  useMessage,
} from "naive-ui";
import EmptyState from "../../shared/components/EmptyState.vue";
import {
  checkPushWebhook,
  deletePushSubscription,
  getPushTypes,
  listPushSubscriptions,
  maskPushText,
  maskPushUrl,
  pushEventLabel,
  pushSubscriptionsFromResponse,
  pushSubscriptionNumericId,
  pushTypesFromResponse,
  PUSH_EVENT_FALLBACK_TYPES,
  setPushSubscription,
  setPushSubscriptionEnabled,
} from "./api";
import { getErrorMessage } from "../../shared/api/client";
import { useShop } from "../../shared/composables/useShop";
import type { PushShopState, PushSubscription } from "./types";
import type { ShopId } from "../../shared/types/common";
import { formatBeijingDateTime } from "../../shared/utils/format";

const message = useMessage();
const dialog = useDialog();
const { shops } = useShop();
const shopIds: ShopId[] = [1, 2];
const shopStates = reactive<Record<ShopId, PushShopState>>({
  1: createShopState(1),
  2: createShopState(2),
});
const loadRequestIds: Record<ShopId, number> = { 1: 0, 2: 0 };
let viewActive = false;
let viewToken = 0;

function createShopState(shopId: ShopId): PushShopState {
  return {
    shopId,
    loading: true,
    apiAvailable: false,
    listReady: false,
    types: [],
    typesFresh: false,
    subscriptions: [],
    typeError: "",
    listError: "",
    selectedTypes: [],
    urlDraft: "",
    setting: false,
    setError: "",
    enableBusyIds: [],
    enableError: "",
    deletingIds: [],
    deleteError: "",
    check: { status: "idle", message: "" },
  };
}

function shopState(shopId: ShopId): PushShopState {
  return shopStates[shopId];
}

function shopName(shopId: ShopId): string {
  return shops.value.find((shop) => shop.id === shopId)?.name ?? `店铺 ${shopId}`;
}

function displayError(error: unknown): string {
  return maskPushText(getErrorMessage(error));
}

function isCurrentView(token: number): boolean {
  return viewActive && token === viewToken;
}

function rejectedMessage(result: PromiseSettledResult<unknown>): string {
  return result.status === "rejected" ? displayError(result.reason) : "";
}

function currentSubscriptionUrl(data: PushShopState): string {
  const row = data.subscriptions.find((subscription) => subscription.url);
  return row ? maskPushUrl(row.url) : data.listReady ? "暂无" : "无法读取";
}

function extraSubscriptionCount(data: PushShopState): number {
  return Math.max(0, data.subscriptions.filter((subscription) => subscription.url).length - 1);
}

function subscriptionStatus(data: PushShopState): string {
  if (!data.listReady) return "无法读取";
  return data.subscriptions.length ? "已配置" : "未配置";
}

/* Macaron tone roles (DESIGN.md §colors.tones): mint = 已配置/可用,
   lavender = 未配置待设置, peach = 读取失败/不可用。 */
function subscriptionStatusTone(data: PushShopState): "mint" | "lavender" | "peach" {
  if (!data.listReady) return "peach";
  return data.subscriptions.length ? "mint" : "lavender";
}

function subscriptionCount(data: PushShopState): string {
  return data.listReady ? String(data.subscriptions.length) : "—";
}

function enabledCount(data: PushShopState): string {
  return data.listReady ? String(data.subscriptions.filter((row) => row.enabled).length) : "—";
}

function selectedType(data: PushShopState, type: string): boolean {
  return data.selectedTypes.includes(type);
}

function updateSelectedType(data: PushShopState, type: string, checked: boolean): void {
  data.selectedTypes = checked
    ? [...new Set([...data.selectedTypes, type])]
    : data.selectedTypes.filter((value) => value !== type);
  data.setError = "";
}

function isEnableBusy(data: PushShopState, row: PushSubscription): boolean {
  return row.id !== null && data.enableBusyIds.includes(String(row.id));
}

function isDeleting(data: PushShopState, row: PushSubscription): boolean {
  return row.id !== null && data.deletingIds.includes(String(row.id));
}

function setValidationError(data: PushShopState, text: string): void {
  data.setError = text;
  message.error(text);
}

async function loadShop(shopId: ShopId): Promise<void> {
  const requestId = ++loadRequestIds[shopId];
  const data = shopState(shopId);
  Object.assign(data, {
    loading: true,
    apiAvailable: false,
    listReady: false,
    types: [],
    typesFresh: false,
    subscriptions: [],
    typeError: "",
    listError: "",
    setting: false,
    setError: "",
    enableBusyIds: [],
    enableError: "",
    deletingIds: [],
    deleteError: "",
    check: { status: "idle", message: "" },
  });

  const [typesResult, listResult] = await Promise.allSettled([
    getPushTypes(shopId),
    listPushSubscriptions(shopId),
  ]);
  if (!viewActive || requestId !== loadRequestIds[shopId]) return;

  const typesOk = typesResult.status === "fulfilled";
  const listOk = listResult.status === "fulfilled";
  const ozonTypes = typesOk ? pushTypesFromResponse(typesResult.value) : [];
  const subscriptions = listOk ? pushSubscriptionsFromResponse(listResult.value) : [];
  const subscriptionTypes = subscriptions.flatMap((subscription) => subscription.types);
  const baseTypes = ozonTypes.length ? ozonTypes : PUSH_EVENT_FALLBACK_TYPES;
  const types = [...new Set([...baseTypes, ...subscriptionTypes])];
  const firstSubscriptionTypes = subscriptions.find((subscription) => subscription.types.length)?.types ?? [];
  const previousTypes = data.selectedTypes.filter((type) => types.includes(type));

  Object.assign(data, {
    loading: false,
    apiAvailable: typesOk || listOk,
    listReady: listOk,
    types,
    typesFresh: typesOk && ozonTypes.length > 0,
    subscriptions,
    typeError: typesOk
      ? ozonTypes.length ? "" : "Ozon 未返回可订阅类型"
      : rejectedMessage(typesResult),
    listError: listOk ? "" : rejectedMessage(listResult),
    selectedTypes: firstSubscriptionTypes.length
      ? firstSubscriptionTypes
      : previousTypes.length ? previousTypes : types,
  });
}

async function loadPushSubscriptions(): Promise<void> {
  viewActive = true;
  viewToken += 1;
  await Promise.all(shopIds.map((shopId) => loadShop(shopId)));
}

async function runCheck(shopId: ShopId): Promise<void> {
  const token = viewToken;
  const data = shopState(shopId);
  const url = data.urlDraft.trim();
  data.urlDraft = url;
  if (!url) {
    data.check = { status: "error", message: "请输入 Webhook 地址" };
    message.error(data.check.message);
    return;
  }
  if (!url.startsWith("https://")) {
    data.check = { status: "error", message: "Webhook 地址必须以 https:// 开头" };
    message.error(data.check.message);
    return;
  }

  data.check = { status: "loading", message: "" };
  data.setError = "";
  try {
    await checkPushWebhook(shopId, url);
    if (!isCurrentView(token)) return;
    data.check = { status: "success", message: "检测成功：Ozon 已接受 Webhook 地址" };
  } catch (error) {
    if (!isCurrentView(token)) return;
    data.check = { status: "error", message: displayError(error) };
    message.error(data.check.message);
  }
}

async function saveSubscription(shopId: ShopId): Promise<void> {
  const token = viewToken;
  const data = shopState(shopId);
  if (data.setting) return;
  const url = data.urlDraft.trim();
  const types = [...data.selectedTypes];
  data.urlDraft = url;
  data.selectedTypes = types;
  data.setError = "";
  if (!url) return setValidationError(data, "请输入 Webhook 地址");
  if (!url.startsWith("https://")) return setValidationError(data, "Webhook 地址必须以 https:// 开头");
  if (!types.length) return setValidationError(data, "至少选择一个 Push 类型");

  const existing = data.subscriptions.some((subscription) => subscription.url === url);
  data.setting = true;
  try {
    await setPushSubscription(shopId, url, types);
    if (!isCurrentView(token)) return;
    message.success(existing ? "Push 订阅已更新" : "Push 订阅已注册");
    data.urlDraft = "";
    await loadShop(shopId);
  } catch (error) {
    if (!isCurrentView(token)) return;
    data.setError = displayError(error);
    message.error(data.setError);
  } finally {
    if (isCurrentView(token)) data.setting = false;
  }
}

async function toggleSubscription(shopId: ShopId, row: PushSubscription, enabled: boolean): Promise<void> {
  const token = viewToken;
  const data = shopState(shopId);
  const id = pushSubscriptionNumericId(row.id);
  if (id === null) {
    data.enableError = "通知ID无效";
    message.error(data.enableError);
    return;
  }
  const key = String(row.id);
  if (data.enableBusyIds.includes(key)) return;
  const previous = row.enabled;
  row.enabled = enabled;
  data.enableBusyIds = [...data.enableBusyIds, key];
  data.enableError = "";
  try {
    await setPushSubscriptionEnabled(shopId, id, enabled);
    if (!isCurrentView(token)) return;
    message.success(enabled ? "Push 订阅已启用" : "Push 订阅已停用");
    await loadShop(shopId);
  } catch (error) {
    if (!isCurrentView(token)) return;
    row.enabled = previous;
    data.enableError = displayError(error);
    message.error(data.enableError);
  } finally {
    if (isCurrentView(token)) data.enableBusyIds = data.enableBusyIds.filter((value) => value !== key);
  }
}

async function confirmDelete(row: PushSubscription): Promise<boolean> {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value: boolean): void => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    dialog.warning({
      title: "删除 Push 订阅？",
      content: `将从 Ozon 删除订阅 ID ${row.id ?? "—"}，此操作不可撤销。`,
      positiveText: "确认删除",
      negativeText: "取消",
      onPositiveClick: () => finish(true),
      onNegativeClick: () => finish(false),
      onClose: () => finish(false),
    });
  });
}

async function removeSubscription(shopId: ShopId, row: PushSubscription): Promise<void> {
  const token = viewToken;
  const data = shopState(shopId);
  const id = pushSubscriptionNumericId(row.id);
  if (id === null) {
    data.deleteError = "通知ID无效";
    message.error(data.deleteError);
    return;
  }
  if (!(await confirmDelete(row)) || !isCurrentView(token)) return;

  const key = String(row.id);
  if (data.deletingIds.includes(key)) return;
  data.deletingIds = [...data.deletingIds, key];
  data.deleteError = "";
  try {
    await deletePushSubscription(shopId, id);
    if (!isCurrentView(token)) return;
    message.success("Push 订阅已删除");
    await loadShop(shopId);
  } catch (error) {
    if (!isCurrentView(token)) return;
    data.deleteError = displayError(error);
    message.error(data.deleteError);
  } finally {
    if (isCurrentView(token)) data.deletingIds = data.deletingIds.filter((value) => value !== key);
  }
}

onMounted(() => { void loadPushSubscriptions(); });
onBeforeUnmount(() => {
  viewActive = false;
  viewToken += 1;
  loadRequestIds[1] += 1;
  loadRequestIds[2] += 1;
});
</script>

<template>
  <section class="push-view">
    <NCard :bordered="false" class="analytics-table-card push-intro-card">
      <div class="push-intro">
        <span class="push-intro-icon" aria-hidden="true"><morph-icon icon="zap" size="20" stroke-width="1.8" /></span>
        <div>
          <strong>通过 Ozon Push 实时接收订单、状态和库存变化。</strong>
          <p>Webhook 密钥由服务器环境变量管理。</p>
          <small>Webhook 地址必须能够被 Ozon 通过公网 HTTPS 访问；密钥由服务器 .env 管理，请勿在页面中展示或保存 Secret。</small>
        </div>
      </div>
    </NCard>

    <div class="push-shop-grid">
      <NCard v-for="shopId in shopIds" :key="shopId" :bordered="false" class="analytics-table-card push-shop-card">
        <template #header>
          <div class="analytics-panel-heading push-card-heading">
            <div>
              <h2><morph-icon icon="store" size="18" stroke-width="1.8" />{{ shopName(shopId) }}</h2>
              <span>店铺 {{ shopId }} · 单独管理 Seller API Push 订阅</span>
            </div>
            <NTag
              v-if="shopState(shopId).loading"
              size="small"
              round
              :bordered="false"
              class="push-tone-tag--lavender"
            >
              读取中
            </NTag>
            <NTag
              v-else
              size="small"
              round
              :bordered="false"
              :class="`push-tone-tag--${subscriptionStatusTone(shopState(shopId))}`"
            >
              {{ subscriptionStatus(shopState(shopId)) }}
            </NTag>
          </div>
        </template>

        <template v-if="shopState(shopId).loading">
          <div class="push-status-grid" aria-busy="true">
            <div v-for="i in 4" :key="i" class="push-status-item">
              <NSkeleton text width="45%" />
              <NSkeleton text width="70%" class="kpi-skeleton-value" />
            </div>
            <div class="push-status-item push-status-url">
              <NSkeleton text width="36%" />
              <NSkeleton text width="88%" />
            </div>
          </div>
          <div class="push-form-skeleton">
            <NSkeleton text :repeat="4" width="64%" />
          </div>
        </template>

        <template v-else>
          <div class="push-status-grid">
            <div class="push-status-item">
              <span>Ozon API</span>
              <NTag size="small" round :bordered="false" :class="shopState(shopId).apiAvailable ? 'push-tone-tag--mint' : 'push-tone-tag--peach'">
                {{ shopState(shopId).apiAvailable ? "可用" : "不可用" }}
              </NTag>
            </div>
            <div class="push-status-item">
              <span>订阅数量</span>
              <strong>{{ subscriptionCount(shopState(shopId)) }}</strong>
            </div>
            <div class="push-status-item">
              <span>已启用数量</span>
              <strong>{{ enabledCount(shopState(shopId)) }}</strong>
            </div>
            <div class="push-status-item push-status-url">
              <span>当前订阅 URL</span>
              <code title="Webhook 地址已隐藏密钥">{{ currentSubscriptionUrl(shopState(shopId)) }}</code>
              <small v-if="extraSubscriptionCount(shopState(shopId))">另有 {{ extraSubscriptionCount(shopState(shopId)) }} 个订阅</small>
            </div>
          </div>

          <NAlert v-if="!shopState(shopId).apiAvailable" type="error" class="push-alert" title="Ozon Push 管理 API 不可用">
            {{ shopState(shopId).typeError || shopState(shopId).listError || "请检查服务器中的 Ozon API 凭据" }}
          </NAlert>

          <NCard :bordered="false" class="push-form-card">
            <template #header>
              <div class="push-section-heading">
                <div>
                  <h3>Webhook 地址</h3>
                  <span>向 Ozon 注册订阅时使用的公网 HTTPS 地址</span>
                </div>
              </div>
            </template>
            <form class="push-form" @submit.prevent="saveSubscription(shopId)">
              <label class="push-field">
                <span>Webhook URL</span>
                <NInput v-model:value="shopState(shopId).urlDraft" placeholder="https://example.com/api/webhooks/ozon/…" autocomplete="off" />
              </label>

              <div class="push-section-heading">
                <div>
                  <h3>订阅事件</h3>
                  <span>提交给 Ozon API 的是原始 <code>TYPE_*</code> 值</span>
                </div>
              </div>
              <NAlert v-if="!shopState(shopId).typesFresh" type="warning" class="push-alert">
                无法从 Ozon 获取最新类型，已使用内置已知类型作为降级展示。
                <span v-if="shopState(shopId).typeError">{{ shopState(shopId).typeError }}</span>
              </NAlert>
              <div v-if="shopState(shopId).types.length" class="push-type-list">
                <NCheckbox
                  v-for="type in shopState(shopId).types"
                  :key="type"
                  class="push-type-option"
                  :checked="selectedType(shopState(shopId), type)"
                  @update:checked="updateSelectedType(shopState(shopId), type, $event)"
                >
                  <span class="push-type-copy">
                    <strong>{{ pushEventLabel(type) }}</strong>
                    <code>{{ type }}</code>
                  </span>
                </NCheckbox>
              </div>
              <EmptyState v-else title="Ozon 未返回可订阅类型" icon="bolt" />

              <div class="push-form-actions">
                <NButton type="default" :loading="shopState(shopId).check.status === 'loading'" :disabled="shopState(shopId).check.status === 'loading'" @click="runCheck(shopId)">
                  <template #icon><morph-icon icon="sync" size="14" stroke-width="2" /></template>
                  检测连接
                </NButton>
                <NButton type="primary" attr-type="submit" :loading="shopState(shopId).setting">
                  <template #icon><morph-icon :icon="shopState(shopId).subscriptions.some((row) => row.url === shopState(shopId).urlDraft.trim()) ? 'edit' : 'plus'" size="14" stroke-width="2" /></template>
                  {{ shopState(shopId).subscriptions.some((row) => row.url === shopState(shopId).urlDraft.trim()) ? "更新订阅" : "注册订阅" }}
                </NButton>
              </div>
              <NAlert v-if="shopState(shopId).check.status !== 'idle'" :type="shopState(shopId).check.status === 'success' ? 'success' : shopState(shopId).check.status === 'error' ? 'error' : 'info'" class="push-alert" role="status">
                {{ shopState(shopId).check.status === 'loading' ? '正在请求 Ozon 检测 Webhook…' : shopState(shopId).check.message }}
              </NAlert>
              <NAlert v-if="shopState(shopId).setError" type="error" class="push-alert" title="Push 订阅保存失败">
                {{ shopState(shopId).setError }}
              </NAlert>
            </form>
          </NCard>

          <section class="push-subscription-section">
            <div class="push-section-heading">
              <div>
                <h3>当前订阅</h3>
                <span>Ozon API 返回的订阅列表</span>
              </div>
              <NTag size="small" round :bordered="false" type="default">{{ shopState(shopId).listReady ? `${shopState(shopId).subscriptions.length} 条` : "读取中" }}</NTag>
            </div>

            <NAlert v-if="!shopState(shopId).listReady" type="error" class="push-alert" title="订阅读取失败">
              {{ shopState(shopId).listError || "Ozon 未返回订阅列表" }}
            </NAlert>
            <EmptyState v-else-if="!shopState(shopId).subscriptions.length" icon="zap" title="暂无 Push 订阅" hint="填写 Webhook 地址并选择事件后即可注册。" />
            <div v-else class="push-subscription-list">
              <article v-for="row in shopState(shopId).subscriptions" :key="`${shopId}-${row.id ?? row.url}`" class="push-subscription">
                <div class="push-subscription-main">
                  <div class="push-subscription-id"><span>ID</span><code>{{ row.id ?? "—" }}</code></div>
                  <code class="push-subscription-url" title="Webhook 地址已隐藏密钥">{{ maskPushUrl(row.url) }}</code>
                  <div class="push-subscription-types">
                    <NTag
                      v-for="type in row.types"
                      :key="type"
                      size="small"
                      round
                      :bordered="false"
                      class="push-tone-tag--azure"
                      :title="type"
                    >
                      {{ pushEventLabel(type) === "Ozon Push 事件" ? type : pushEventLabel(type) }}
                    </NTag>
                    <span v-if="!row.types.length" class="push-muted">未返回事件类型</span>
                  </div>
                  <div class="push-subscription-details">
                    <span v-if="row.createdAt">创建于 {{ formatBeijingDateTime(row.createdAt) }}</span>
                    <span v-if="row.updatedAt">更新于 {{ formatBeijingDateTime(row.updatedAt) }}</span>
                    <span v-if="row.error">Ozon：{{ maskPushText(row.error) }}</span>
                  </div>
                </div>
                <div class="push-subscription-actions">
                  <label class="push-enable-control">
                    <span>启用</span>
                    <NSwitch
                      :value="row.enabled"
                      :disabled="isEnableBusy(shopState(shopId), row)"
                      @update:value="toggleSubscription(shopId, row, $event)"
                    />
                  </label>
                  <NButton
                    size="small"
                    text
                    type="error"
                    :loading="isDeleting(shopState(shopId), row)"
                    :disabled="isDeleting(shopState(shopId), row)"
                    @click="removeSubscription(shopId, row)"
                  >
                    <template #icon><morph-icon icon="trash" size="12" stroke-width="2" /></template>
                    {{ isDeleting(shopState(shopId), row) ? "删除中…" : "删除" }}
                  </NButton>
                </div>
              </article>
            </div>
            <NAlert v-if="shopState(shopId).enableError" type="error" class="push-alert" title="Push 订阅启停失败">
              {{ shopState(shopId).enableError }}
            </NAlert>
            <NAlert v-if="shopState(shopId).deleteError" type="error" class="push-alert" title="Push 订阅删除失败">
              {{ shopState(shopId).deleteError }}
            </NAlert>
          </section>
        </template>
      </NCard>
    </div>
  </section>
</template>
