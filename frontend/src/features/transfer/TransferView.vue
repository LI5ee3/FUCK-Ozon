<script setup lang="ts">
import "./transfer.css";
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import type { IconName } from "../../shared/icons/tabler";
import { NButton, NCard, NDatePicker, NEmpty, NSelect, NSpin } from "naive-ui";
import { getErrorMessage } from "../../shared/api/client";
import {
  buildExportUrl,
  getImportHistory,
  importCsv,
  type ExportModule,
  type ImportHistoryItem,
  type ImportKind,
} from "./api";
import { useShop } from "../../shared/composables/useShop";
import { beijingThreeMonthRange, parseValidDateRange, standardDatePresetRange, type DateRange, type StandardDatePreset } from "../../shared/utils/date";
import { formatBeijingDateTime, formatInteger, formatNumber } from "../../shared/utils/format";
import type { ShopId } from "../../shared/types/common";

const MAX_FILE_BYTES = 50 * 1024 * 1024;

type DatePreset = StandardDatePreset;
type ImportStatusTone = "muted" | "success" | "error";
type FileValidation = { valid: boolean; detail: string; status: string };

const { shops, selectedShopId } = useShop();
const fileInput = ref<HTMLInputElement | null>(null);
const selectedFile = ref<File | null>(null);
const importShop = ref<ShopId | null>(null);
const importKind = ref<ImportKind | null>(null);
const importing = ref(false);
const isDragging = ref(false);
const importStatusOverride = ref("");
const importStatusTone = ref<ImportStatusTone>("muted");
const historyRows = ref<ImportHistoryItem[]>([]);
const historyLoading = ref(false);
const historyError = ref("");
const exportRange = ref<DateRange>(beijingThreeMonthRange());
const exportPreparing = reactive<Record<ExportModule, boolean>>({
  orders: false,
  risk: false,
  returns: false,
  complaints: false,
});

let viewActive = true;
let historyRequestId = 0;
let importRequestId = 0;
const exportResetTimers: Partial<Record<ExportModule, number>> = {};

const importShopOptions = computed(() => shops.value.map((shop) => ({ label: shop.name, value: shop.id })));
const importKindOptions: Array<{ label: string; value: ImportKind }> = [
  { label: "FBP (菜鸟认证仓)", value: "FBP" },
  { label: "realFBS (第三方自发货)", value: "realFBS" },
  { label: "WHD (全托管/官方退货)", value: "WHD" },
];
const exportModules: ReadonlyArray<{
  module: ExportModule;
  title: string;
  description: string;
  icon: IconName;
  tone: "butter" | "peach" | "lavender" | "mint";
}> = [
  { module: "orders", title: "订单数据", description: "包含订单号、履约渠道、创单时间、发货状态及交易金额", icon: "package", tone: "butter" },
  { module: "risk", title: "取消与风险分析", description: "包含 SKU、渠道、货件及固定取消原因结构化数据", icon: "alertTriangle", tone: "peach" },
  { module: "returns", title: "退货与异常订单", description: "包含取消记录、客户退货申请及处理流转数据", icon: "rotateCcw", tone: "lavender" },
  { module: "complaints", title: "异常投诉与赔付", description: "包含投诉编号、状态、赔付金额及处理备注", icon: "messageSquareAlert", tone: "mint" },
];
const datePresets: ReadonlyArray<{ key: DatePreset; label: string }> = [
  { key: "today", label: "今天" },
  { key: "3days", label: "3天内" },
  { key: "7days", label: "7天内" },
  { key: "3months", label: "近三个月" },
  { key: "all", label: "全部时间" },
];

const fileValidation = computed<FileValidation>(() => validateFile(selectedFile.value));
const canImport = computed(() => Boolean(
  importShop.value && importKind.value && selectedFile.value && fileValidation.value.valid && !importing.value,
));
const importStatusText = computed(() => {
  if (importing.value) return "正在上传并解析 CSV 数据，请稍候…";
  if (importStatusOverride.value) return importStatusOverride.value;
  if (fileValidation.value.status) return fileValidation.value.status;
  return canImport.value ? "已就绪，点击“开始导入”解析并导入" : "请选择店铺、渠道和 CSV 文件";
});
const importStatusClass = computed(() => `is-${importing.value ? "muted" : importStatusOverride.value ? importStatusTone.value : fileValidation.value.status ? "error" : "muted"}`);
const exportShopName = computed(() => {
  if (selectedShopId.value === 0) return "两店铺合并";
  return shops.value.find((shop) => shop.id === selectedShopId.value)?.name ?? `店铺${selectedShopId.value}`;
});
const exportScope = computed(() => `当前店铺：${exportShopName.value} ｜ 时间范围：${exportRange.value[0]} 至 ${exportRange.value[1]}`);
const activePreset = computed<DatePreset | "">(() => {
  for (const preset of datePresets) {
    const range = standardDatePresetRange(preset.key);
    if (range[0] === exportRange.value[0] && range[1] === exportRange.value[1]) return preset.key;
  }
  return "";
});

function validateFile(file: File | null): FileValidation {
  if (!file) return { valid: false, detail: "支持标准 UTF-8 .csv 文件，单文件上限 50MB", status: "" };
  if (!file.name.toLowerCase().endsWith(".csv")) {
    return { valid: false, detail: "格式不支持，仅允许 .csv 文件", status: "请选择 .csv 格式的文件" };
  }
  if (file.size > MAX_FILE_BYTES) {
    return { valid: false, detail: "文件超过50MB", status: "请选择不超过50MB的 CSV 文件" };
  }
  return {
    valid: true,
    detail: `${formatNumber(file.size / 1024, 1)} KB · CSV 格式验证通过`,
    status: "",
  };
}

function clearImportStatus(): void {
  importStatusOverride.value = "";
  importStatusTone.value = "muted";
}

function selectImportShop(value: string | number | null): void {
  importShop.value = value === 1 || value === "1" || value === 2 || value === "2" ? Number(value) as ShopId : null;
  clearImportStatus();
}

function selectImportKind(value: string | number | null): void {
  importKind.value = value === "FBP" || value === "realFBS" || value === "WHD" ? value : null;
  clearImportStatus();
}

function openFilePicker(): void {
  if (!importing.value) fileInput.value?.click();
}

function selectFile(file: File | null): void {
  selectedFile.value = file;
  isDragging.value = false;
  clearImportStatus();
}

function clearSelectedFile(): void {
  selectedFile.value = null;
  isDragging.value = false;
  if (fileInput.value) fileInput.value.value = "";
}

function handleFileInput(event: Event): void {
  selectFile((event.target as HTMLInputElement).files?.[0] ?? null);
}

function handleDrag(): void {
  if (!importing.value) isDragging.value = true;
}

function handleDragLeave(): void {
  isDragging.value = false;
}

function handleDrop(event: DragEvent): void {
  if (importing.value) return;
  selectFile(event.dataTransfer?.files?.[0] ?? null);
}

async function loadImportHistory(): Promise<void> {
  const currentRequest = ++historyRequestId;
  historyLoading.value = true;
  historyError.value = "";
  try {
    const rows = await getImportHistory();
    if (!viewActive || currentRequest !== historyRequestId) return;
    historyRows.value = rows;
  } catch (cause: unknown) {
    if (!viewActive || currentRequest !== historyRequestId) return;
    historyError.value = getErrorMessage(cause);
  } finally {
    if (viewActive && currentRequest === historyRequestId) historyLoading.value = false;
  }
}

async function submitImport(): Promise<void> {
  const shopId = importShop.value;
  const kind = importKind.value;
  const file = selectedFile.value;
  if (importing.value || !shopId || !kind || !file || !fileValidation.value.valid) return;

  const currentRequest = ++importRequestId;
  importing.value = true;
  try {
    const result = await importCsv(kind, shopId, file);
    if (!viewActive || currentRequest !== importRequestId) return;
    clearSelectedFile();
    importStatusOverride.value = `成功导入 ${formatInteger(result.rows)} 行数据`;
    importStatusTone.value = "success";
    importing.value = false;
    await loadImportHistory();
  } catch (cause: unknown) {
    if (!viewActive || currentRequest !== importRequestId) return;
    importStatusOverride.value = `导入失败：${getErrorMessage(cause)}`;
    importStatusTone.value = "error";
  } finally {
    if (viewActive && currentRequest === importRequestId) importing.value = false;
  }
}

function handleDateRangeChange(value: string | DateRange | null): void {
  if (!Array.isArray(value) || value.length !== 2 || typeof value[0] !== "string" || typeof value[1] !== "string") return;
  const fallback = beijingThreeMonthRange();
  const next = parseValidDateRange(value[0], value[1], fallback);
  if (next[0] !== value[0] || next[1] !== value[1]) return;
  exportRange.value = next;
}

function selectPreset(preset: DatePreset): void {
  exportRange.value = standardDatePresetRange(preset);
}

function startExport(module: ExportModule): void {
  if (exportPreparing[module]) return;
  exportPreparing[module] = true;
  window.location.assign(buildExportUrl(module, selectedShopId.value, exportRange.value[0], exportRange.value[1]));
  exportResetTimers[module] = window.setTimeout(() => {
    if (viewActive) exportPreparing[module] = false;
  }, 1000);
}

onMounted(() => {
  void loadImportHistory();
});

onBeforeUnmount(() => {
  viewActive = false;
  historyRequestId += 1;
  importRequestId += 1;
  for (const timer of Object.values(exportResetTimers)) {
    if (timer !== undefined) window.clearTimeout(timer);
  }
});
</script>

<template>
  <section class="transfer-view">
    <div class="transfer-grid">
      <NCard :bordered="false" class="transfer-card transfer-import-card">
        <template #header>
          <div class="transfer-panel-heading">
            <div>
              <h2><morph-icon icon="uploadCloud" size="18" stroke-width="1.8" />CSV 历史数据导入</h2>
              <span>仅补充 API 缺失的历史订单数据，时间按 UTC 解析</span>
            </div>
          </div>
        </template>
        <form class="transfer-import-form" @submit.prevent="submitImport">
          <div class="transfer-import-steps">
            <label class="transfer-step">
              <span class="transfer-step-heading"><b>1</b><strong>选择目标店铺</strong></span>
              <NSelect
                :value="importShop"
                :options="importShopOptions"
                placeholder="请选择店铺"
                aria-label="导入店铺"
                :disabled="importing"
                @update:value="selectImportShop"
              />
            </label>

            <label class="transfer-step">
              <span class="transfer-step-heading"><b>2</b><strong>选择履约渠道</strong></span>
              <NSelect
                :value="importKind"
                :options="importKindOptions"
                placeholder="请选择渠道"
                aria-label="导入渠道"
                :disabled="importing"
                @update:value="selectImportKind"
              />
            </label>

            <div class="transfer-step">
              <span class="transfer-step-heading"><b>3</b><strong>上传 CSV 数据文件</strong></span>
              <div
                class="transfer-file-panel"
                :class="{ 'is-dragging': isDragging, 'is-invalid': selectedFile && !fileValidation.valid, 'is-ready': fileValidation.valid }"
                role="button"
                tabindex="0"
                aria-label="选择或拖拽 CSV 文件"
                :aria-disabled="importing"
                @click="openFilePicker"
                @keydown.enter.prevent="openFilePicker"
                @keydown.space.prevent="openFilePicker"
                @dragenter.prevent="handleDrag"
                @dragover.prevent="handleDrag"
                @dragleave.prevent="handleDragLeave"
                @drop.prevent="handleDrop"
              >
                <input ref="fileInput" class="transfer-file-input" type="file" accept=".csv,text/csv" :disabled="importing" @change="handleFileInput" />
                <span class="transfer-file-icon"><morph-icon :icon="selectedFile && !fileValidation.valid ? 'alertTriangle' : fileValidation.valid ? 'fileText' : 'uploadCloud'" size="24" stroke-width="1.8" /></span>
                <span class="transfer-file-meta">
                  <strong class="transfer-file-name" :title="selectedFile?.name">{{ selectedFile?.name ?? "点击选择或将 CSV 文件拖拽至此处" }}</strong>
                  <small>{{ selectedFile ? fileValidation.detail : "支持标准 UTF-8 .csv 文件，单文件上限 50MB" }}</small>
                </span>
                <NButton type="default" size="small" attr-type="button" :disabled="importing" @click.stop="openFilePicker">
                  <template #icon><morph-icon icon="folder" size="14" stroke-width="1.8" /></template>
                  {{ selectedFile ? "更换文件" : "选择文件" }}
                </NButton>
              </div>
            </div>
          </div>

          <div class="transfer-import-actions">
            <NButton type="primary" attr-type="submit" :loading="importing" :disabled="!canImport">
              <template #icon><morph-icon icon="upload" size="14" stroke-width="2" /></template>
              {{ importing ? "正在导入…" : "开始导入" }}
            </NButton>
            <span class="transfer-import-status" :class="importStatusClass" role="status" aria-live="polite">{{ importStatusText }}</span>
          </div>
        </form>
      </NCard>

      <NCard :bordered="false" class="transfer-card transfer-export-card">
        <template #header>
          <div class="transfer-panel-heading">
            <div>
              <h2><morph-icon icon="download" size="18" stroke-width="1.8" />结构化数据导出</h2>
              <span>保留适合 AI 深度分析的结构化字段，敏感密钥与隐私信息已自动脱敏</span>
            </div>
          </div>
        </template>
        <div class="transfer-date-controls">
          <span class="transfer-control-label">导出日期</span>
          <NDatePicker
            :formatted-value="exportRange"
            type="daterange"
            value-format="yyyy-MM-dd"
            separator="至"
            :clearable="false"
            class="transfer-date-picker"
            aria-label="导出日期范围"
            @update:formatted-value="handleDateRangeChange"
          />
          <div class="transfer-date-presets" aria-label="日期快捷范围">
            <NButton
              v-for="preset in datePresets"
              :key="preset.key"
              size="small"
              attr-type="button"
              :type="activePreset === preset.key ? 'primary' : 'default'"
              :secondary="activePreset !== preset.key"
              @click="selectPreset(preset.key)"
            >
              {{ preset.label }}
            </NButton>
          </div>
        </div>
        <div class="transfer-scope-banner">
          <div class="transfer-scope-info">
            <morph-icon icon="calendar" size="15" stroke-width="1.8" />
            <p>{{ exportScope }}</p>
          </div>
          <small>受顶部全局店铺与时间筛选影响</small>
        </div>
        <div class="transfer-export-grid">
          <article v-for="item in exportModules" :key="item.module" class="transfer-export-module" :class="`transfer-accent-${item.tone}`">
            <div class="transfer-export-head">
              <strong>{{ item.title }}</strong>
              <span class="transfer-export-icon"><morph-icon :icon="item.icon" size="15" stroke-width="2" /></span>
            </div>
            <p>{{ item.description }}</p>
            <div class="transfer-export-foot">
              <span class="transfer-format-tag">JSONL · AI友好</span>
              <NButton
                class="transfer-export-button"
                size="small"
                attr-type="button"
                :loading="exportPreparing[item.module]"
                :disabled="exportPreparing[item.module]"
                @click="startExport(item.module)"
              >
                <template #icon><morph-icon icon="download" size="13" stroke-width="2" /></template>
                {{ exportPreparing[item.module] ? "正在准备…" : "导出数据" }}
              </NButton>
            </div>
          </article>
        </div>
      </NCard>
    </div>

    <NCard :bordered="false" class="transfer-card transfer-history-card">
      <template #header>
        <div class="transfer-panel-heading">
          <div>
            <h2><morph-icon icon="clock" size="18" stroke-width="1.8" />最近导入记录</h2>
            <span>保留最近 10 次 CSV 导入记录，不受时间范围影响</span>
          </div>
          <span v-if="historyLoading && historyRows.length" class="transfer-history-refresh"><NSpin size="small" />刷新中…</span>
        </div>
      </template>
      <div v-if="historyError && historyRows.length" class="transfer-history-error" role="alert">导入记录加载失败：{{ historyError }}</div>
      <div class="transfer-history-table-wrap">
        <table class="transfer-history-table">
          <thead>
            <tr><th>文件名称</th><th>所属店铺／渠道</th><th class="is-number">导入行数</th><th class="is-number">导入时间 (北京时间)</th></tr>
          </thead>
          <tbody>
            <template v-if="historyRows.length">
              <tr v-for="row in historyRows" :key="row.id">
                <td>
                  <div class="transfer-history-file">
                    <span class="transfer-history-file-icon"><morph-icon icon="fileText" size="14" stroke-width="1.8" /></span>
                    <strong :title="row.filename">{{ row.filename }}</strong>
                  </div>
                </td>
                <td>
                  <div class="transfer-history-shop"><strong>{{ row.shop_name }}</strong><span class="transfer-channel-tag" :class="`is-${row.kind}`">{{ row.kind }}</span></div>
                </td>
                <td class="is-number"><strong>{{ formatInteger(row.row_count) }}</strong> <small>行</small></td>
                <td class="is-number">{{ formatBeijingDateTime(row.imported_at) }}</td>
              </tr>
            </template>
            <tr v-else-if="historyLoading"><td colspan="4" class="transfer-history-state"><NSpin size="small" /><span>导入记录加载中…</span></td></tr>
            <tr v-else-if="historyError"><td colspan="4" class="transfer-history-state is-error"><morph-icon icon="alertTriangle" size="20" stroke-width="1.8" /><span>导入记录加载失败：{{ historyError }}</span></td></tr>
            <tr v-else><td colspan="4" class="transfer-history-state"><NEmpty description="暂无历史 CSV 导入记录" /></td></tr>
          </tbody>
        </table>
      </div>
    </NCard>
  </section>
</template>
