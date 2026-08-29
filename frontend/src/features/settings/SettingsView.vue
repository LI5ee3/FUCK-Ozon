<script setup lang="ts">
import "./settings.css";
import { onBeforeUnmount, onMounted, reactive, ref } from "vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import {
  NAlert,
  NButton,
  NCard,
  NInput,
  NRadioButton,
  NRadioGroup,
  NSpin,
  NTag,
  useMessage,
} from "naive-ui";
import { probeShop } from "./api";
import { getErrorMessage } from "../../shared/api/client";
import { updateShops } from "../../shared/api/shops";
import { useShop } from "../../shared/composables/useShop";
import { useTheme, type ThemeMode } from "../../shared/composables/useTheme";
import type { OzonProbePermissions, OzonProbeResponse, OzonProbeStatus } from "./types";
import type { ShopId } from "../../shared/types/common";
import { copyText } from "../../shared/utils/clipboard";

type ShopNames = { 1: string; 2: string };
type ProbeState = { status: OzonProbeStatus; response: OzonProbeResponse | null; error: string };
type PermissionKey = keyof OzonProbePermissions;

const shopIds: ShopId[] = [1, 2];
const themeOptions: Array<{ label: string; value: ThemeMode }> = [
  { label: "跟随系统", value: "system" },
  { label: "浅色模式", value: "light" },
  { label: "深色模式", value: "dark" },
];
const permissionOptions: Array<{ key: PermissionKey; label: string }> = [
  { key: "orders", label: "订单" },
  { key: "returns", label: "退货" },
  { key: "stock", label: "库存" },
];
const statusLabels: Record<OzonProbeStatus, string> = {
  idle: "待检测",
  loading: "正在检测…",
  success: "凭据有效",
  error: "连接失败",
};

const message = useMessage();
const { mode, setMode } = useTheme();
const { shops, load: loadShops } = useShop();
const shopNames = reactive<ShopNames>({ 1: "", 2: "" });
const savedNames = reactive<ShopNames>({ 1: "", 2: "" });
const shopLoading = ref(true);
const shopNamesLoaded = ref(false);
const loadError = ref("");
const savingShopNames = ref(false);
const probeAllLoading = ref(false);
const probeStates = reactive<Record<ShopId, ProbeState>>({
  1: { status: "idle", response: null, error: "" },
  2: { status: "idle", response: null, error: "" },
});
const probeRequestIds: Record<ShopId, number> = { 1: 0, 2: 0 };
let shopRequestId = 0;
let saveRequested = false;
let savePromise: Promise<void> | null = null;
let viewActive = false;

function shopName(shopId: ShopId): string {
  return shops.value.find((shop) => shop.id === shopId)?.name ?? `店铺 ${shopId}`;
}

function applyServerNames(): void {
  for (const shopId of shopIds) {
    const name = shops.value.find((shop) => shop.id === shopId)?.name ?? "";
    shopNames[shopId] = name;
    savedNames[shopId] = name;
  }
}

async function loadShopNames(): Promise<void> {
  const requestId = ++shopRequestId;
  shopLoading.value = true;
  loadError.value = "";
  try {
    if (!shops.value.length) await loadShops();
    if (!viewActive || requestId !== shopRequestId) return;
    applyServerNames();
    shopNamesLoaded.value = true;
  } catch (error) {
    if (viewActive && requestId === shopRequestId) loadError.value = getErrorMessage(error);
  } finally {
    if (viewActive && requestId === shopRequestId) shopLoading.value = false;
  }
}

function changeTheme(value: string | number | null): void {
  if (value !== "system" && value !== "light" && value !== "dark") return;
  setMode(value);
  message.success(`外观已切换为：${themeOptions.find((option) => option.value === value)?.label}`);
}

function currentServerNames(): ShopNames {
  return {
    1: shops.value.find((shop) => shop.id === 1)?.name ?? savedNames[1],
    2: shops.value.find((shop) => shop.id === 2)?.name ?? savedNames[2],
  };
}

function requestShopNameSave(): void {
  if (!shopNamesLoaded.value) return;
  saveRequested = true;
  void saveShopNames();
}

async function saveShopNames(): Promise<void> {
  if (savePromise) return savePromise;
  savePromise = (async () => {
    while (saveRequested && viewActive) {
      saveRequested = false;
      const next: ShopNames = { 1: shopNames[1].trim(), 2: shopNames[2].trim() };
      if (!next[1] || !next[2] || (next[1] === savedNames[1] && next[2] === savedNames[2])) continue;
      savingShopNames.value = true;
      try {
        await updateShops(next);
        if (!viewActive) return;
        await loadShops();
        if (!viewActive) return;
        Object.assign(savedNames, currentServerNames());
        message.success("店铺名称已自动保存");
      } catch (error) {
        if (viewActive) message.error(getErrorMessage(error));
      } finally {
        if (viewActive) savingShopNames.value = false;
      }
    }
  })();
  try {
    await savePromise;
  } finally {
    savePromise = null;
    if (viewActive && saveRequested) void saveShopNames();
  }
}

function probeState(shopId: ShopId): ProbeState {
  return probeStates[shopId];
}

function isCurrentProbe(shopId: ShopId, requestId: number): boolean {
  return viewActive && requestId === probeRequestIds[shopId];
}

async function runProbe(shopId: ShopId, notify = false): Promise<void> {
  const state = probeState(shopId);
  const requestId = ++probeRequestIds[shopId];
  state.status = "loading";
  state.response = null;
  state.error = "";
  try {
    const response = await probeShop(shopId);
    if (!isCurrentProbe(shopId, requestId)) return;
    state.response = response;
    state.status = response.valid ? "success" : "error";
    if (notify) message.info(`店铺 ${shopId} API 检测完成`);
  } catch (error) {
    if (!isCurrentProbe(shopId, requestId)) return;
    state.status = "error";
    state.error = getErrorMessage(error);
    if (notify) message.error(state.error);
  }
}

async function probeAll(): Promise<void> {
  if (probeAllLoading.value) return;
  probeAllLoading.value = true;
  try {
    await Promise.allSettled(shopIds.map((shopId) => runProbe(shopId)));
    if (viewActive) message.success("API 连接与权限检测已完成");
  } finally {
    if (viewActive) probeAllLoading.value = false;
  }
}

function statusType(status: OzonProbeStatus): "default" | "success" | "warning" | "error" {
  if (status === "success") return "success";
  if (status === "error") return "error";
  if (status === "loading") return "warning";
  return "default";
}

function identityValue(response: OzonProbeResponse | null, values: Array<string | number | null | undefined>): string {
  if (!response?.valid) return "—";
  for (const value of values) {
    const text = String(value ?? "").trim();
    if (text) return text;
  }
  return "未返回";
}

function identityName(response: OzonProbeResponse | null): string {
  if (!response?.valid) return "—";
  return identityValue(response, [response.identity?.company?.name, response.identity?.name]) === "未返回"
    ? "店铺身份已确认"
    : identityValue(response, [response.identity?.company?.name, response.identity?.name]);
}

function sellerId(response: OzonProbeResponse | null): string {
  return identityValue(response, [response?.identity?.seller_id, response?.identity?.client_id]);
}

function inn(response: OzonProbeResponse | null): string {
  return identityValue(response, [response?.identity?.company?.inn, response?.identity?.inn]);
}

function roles(response: OzonProbeResponse | null): string {
  if (!response?.valid) return "—";
  return response.roles?.join("、") || "未返回";
}

function probeError(state: ProbeState): string {
  if (state.status !== "error") return "";
  return state.response?.error || state.error || "凭据或网络异常";
}

function permissionValue(state: ProbeState, key: PermissionKey): string {
  if (state.status === "idle" || state.status === "loading") return "待检测";
  return state.response?.permissions?.[key] || (state.status === "success" ? "可用" : "未返回");
}

function permissionType(state: ProbeState, key: PermissionKey): "default" | "success" | "warning" {
  if (state.status === "success" && permissionValue(state, key) === "可用") return "success";
  if (state.status === "idle" || state.status === "loading") return "default";
  return "warning";
}

function copyable(value: string): boolean {
  return value !== "—" && value !== "未返回";
}

async function copyFact(value: string): Promise<void> {
  try {
    await copyText(value);
    message.success(`已复制：${value}`);
  } catch {
    message.error("复制失败");
  }
}

onMounted(() => {
  viewActive = true;
  void loadShopNames();
});

onBeforeUnmount(() => {
  viewActive = false;
  shopRequestId += 1;
  probeRequestIds[1] += 1;
  probeRequestIds[2] += 1;
});
</script>

<template>
  <section class="settings-view">
    <div v-if="shopLoading && !shopNamesLoaded" class="settings-loading" role="status">
      <NSpin size="small" />
      <span>正在读取店铺设置…</span>
    </div>

    <NAlert v-if="loadError" type="error" class="settings-error" title="店铺设置加载失败">
      <div class="settings-error-content">
        <span>{{ loadError }}</span>
        <NButton size="small" :disabled="shopLoading" @click="loadShopNames">重试</NButton>
      </div>
    </NAlert>

    <div class="settings-grid">
      <NCard :bordered="false" class="settings-panel">
        <template #header>
          <div class="settings-panel-heading">
            <div>
              <h2><morph-icon icon="sun" size="18" stroke-width="1.8" />界面与显示偏好</h2>
              <span>控制当前浏览器的界面外观主题与色彩渲染模式</span>
            </div>
          </div>
        </template>
        <div class="settings-body">
          <div class="settings-field-group">
            <span class="settings-label" id="theme-mode-label">外观模式</span>
            <NRadioGroup
              :value="mode"
              name="theme-mode"
              class="settings-theme-control"
              aria-labelledby="theme-mode-label"
              @update:value="changeTheme"
            >
              <NRadioButton v-for="option in themeOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </NRadioButton>
            </NRadioGroup>
          </div>
          <div class="settings-hint-box">
            <morph-icon icon="sparkles" size="15" stroke-width="1.8" />
            <span>采用 Open Macaron 低饱和粉彩与高对比度文字排版，全局支持 Apple HIG 减淡微边框与平滑回弹。</span>
          </div>
        </div>
      </NCard>

      <NCard :bordered="false" class="settings-panel">
        <template #header>
          <div class="settings-panel-heading">
            <div>
              <h2><morph-icon icon="store" size="18" stroke-width="1.8" />店铺展示名称</h2>
              <span>自定义各店铺在数据总览与各模块中的别名</span>
            </div>
          </div>
        </template>
        <form class="settings-body" @submit.prevent="requestShopNameSave">
          <div class="settings-shop-inputs">
            <label class="settings-input-group">
              <span class="settings-input-tag"><morph-icon icon="tag" size="12" stroke-width="2" />店铺 1</span>
              <NInput
                v-model:value="shopNames[1]"
                placeholder="例如：1店 / 莫斯科自营店"
                :disabled="!shopNamesLoaded"
                :input-props="{ required: true }"
                @change="requestShopNameSave"
                @blur="requestShopNameSave"
                @keydown.enter.prevent="requestShopNameSave"
              />
            </label>
            <label class="settings-input-group">
              <span class="settings-input-tag"><morph-icon icon="tag" size="12" stroke-width="2" />店铺 2</span>
              <NInput
                v-model:value="shopNames[2]"
                placeholder="例如：4店 / 圣彼得堡旗舰店"
                :disabled="!shopNamesLoaded"
                :input-props="{ required: true }"
                @change="requestShopNameSave"
                @blur="requestShopNameSave"
                @keydown.enter.prevent="requestShopNameSave"
              />
            </label>
          </div>
          <div v-if="savingShopNames" class="settings-save-status" role="status" aria-live="polite">
            <NSpin size="small" />
            <span>正在保存店铺名称…</span>
          </div>
          <div class="settings-hint-box">
            <morph-icon icon="checkCircle" size="15" stroke-width="1.8" />
            <span>修改店铺名称后，失焦或回车即可自动即时保存并全局同步更新。</span>
          </div>
        </form>
      </NCard>
    </div>

    <NCard :bordered="false" class="settings-api-panel">
      <template #header>
        <div class="settings-panel-heading settings-api-heading">
          <div>
            <h2><morph-icon icon="shieldCheck" size="18" stroke-width="1.8" />API 连接与权限诊断</h2>
            <span>实时检测 Client-Id / Api-Key 凭据、主体身份与各模块接口权限，不同步任何业务数据</span>
          </div>
          <NButton type="primary" :loading="probeAllLoading" @click="probeAll">
            <template #icon><morph-icon icon="sync" size="14" stroke-width="2" /></template>
            一键检测所有店铺
          </NButton>
        </div>
      </template>

      <NAlert type="info" :bordered="false" class="settings-system-banner">
        店铺 API 凭据统一配置于服务器 <code>.env</code> 环境变量；诊断仅执行只读轻量探测，保障凭据安全与零业务干扰。
      </NAlert>

      <div class="settings-shop-grid">
        <article v-for="shopId in shopIds" :key="shopId" class="settings-shop-card">
          <div class="settings-shop-head">
            <div class="settings-shop-identity">
              <span class="settings-shop-badge"><morph-icon icon="store" size="14" stroke-width="2" /><strong>{{ shopName(shopId) }}</strong></span>
              <span class="settings-shop-tag">店铺 {{ shopId }}</span>
            </div>
            <NButton
              size="small"
              secondary
              :loading="probeState(shopId).status === 'loading'"
              :disabled="probeAllLoading"
              title="单独检测 API 连通性"
              @click="runProbe(shopId, true)"
            >
              <template #icon><morph-icon icon="refreshCw" size="12" stroke-width="2" /></template>
              检测
            </NButton>
          </div>

          <div class="settings-probe-result">
            <div class="settings-probe-top">
              <span class="settings-probe-label">诊断状态</span>
              <NTag :type="statusType(probeState(shopId).status)" round :bordered="false">
                {{ statusLabels[probeState(shopId).status] }}
              </NTag>
            </div>

            <div v-if="probeError(probeState(shopId))" class="settings-probe-error" role="alert">
              <morph-icon icon="alertCircle" size="14" stroke-width="2" />
              <span>{{ probeError(probeState(shopId)) }}</span>
            </div>

            <dl class="settings-probe-facts">
              <div>
                <dt>店铺主体</dt>
                <dd>{{ identityName(probeState(shopId).response) }}</dd>
              </div>
              <div>
                <dt>Seller ID</dt>
                <dd>
                  <NButton
                    v-if="copyable(sellerId(probeState(shopId).response))"
                    text
                    size="small"
                    class="settings-copy-button"
                    title="点击复制 Seller ID"
                    @click="copyFact(sellerId(probeState(shopId).response))"
                  >
                    {{ sellerId(probeState(shopId).response) }}
                    <template #icon><morph-icon icon="copy" size="12" stroke-width="1.8" /></template>
                  </NButton>
                  <span v-else>{{ sellerId(probeState(shopId).response) }}</span>
                </dd>
              </div>
              <div>
                <dt>税号 INN</dt>
                <dd>
                  <NButton
                    v-if="copyable(inn(probeState(shopId).response))"
                    text
                    size="small"
                    class="settings-copy-button"
                    title="点击复制 INN"
                    @click="copyFact(inn(probeState(shopId).response))"
                  >
                    {{ inn(probeState(shopId).response) }}
                    <template #icon><morph-icon icon="copy" size="12" stroke-width="1.8" /></template>
                  </NButton>
                  <span v-else>{{ inn(probeState(shopId).response) }}</span>
                </dd>
              </div>
              <div>
                <dt>授权角色</dt>
                <dd>{{ roles(probeState(shopId).response) }}</dd>
              </div>
            </dl>

            <div class="settings-permissions-section">
              <span class="settings-permission-label">模块调用权限</span>
              <div class="settings-permissions">
                <NTag
                  v-for="permission in permissionOptions"
                  :key="permission.key"
                  round
                  :bordered="false"
                  :type="permissionType(probeState(shopId), permission.key)"
                  class="settings-permission"
                >
                  <strong>{{ permission.label }}</strong>
                  <small>{{ permissionValue(probeState(shopId), permission.key) }}</small>
                </NTag>
              </div>
            </div>
          </div>
        </article>
      </div>
    </NCard>
  </section>
</template>
