<script setup lang="ts">
import "../../styles/analytics.css";
import "./dingtalk.css";
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import type { IconName } from "../../shared/icons/tabler";
import {
  NAlert,
  NButton,
  NCard,
  NCheckbox,
  NCheckboxGroup,
  NSkeleton,
  NSpin,
  NSwitch,
  NTag,
  useMessage,
} from "naive-ui";
import { getDingTalkSettings, updateDingTalkSettings } from "./api";
import { getErrorMessage } from "../../shared/api/client";
import type { DingTalkLastRun, DingTalkRunStatus, DingTalkSettings, DingTalkSettingsUpdate } from "./types";
import { formatBeijingDateTime } from "../../shared/utils/format";

type DingTalkTone = "azure" | "peach" | "mint" | "lavender" | "butter";
type SummaryCard = {
  icon: IconName;
  label: string;
  value: string;
  note: string;
  tone: DingTalkTone;
  badge?: string;
};

const weekdays = [
  { value: 1, label: "周一" },
  { value: 2, label: "周二" },
  { value: 3, label: "周三" },
  { value: 4, label: "周四" },
  { value: 5, label: "周五" },
  { value: 6, label: "周六" },
  { value: 7, label: "周日" },
] as const;

const message = useMessage();
const settings = ref<DingTalkSettings | null>(null);
const loading = ref(true);
const saving = ref(false);
const loadError = ref("");
const saveError = ref("");
const form = reactive<DingTalkSettingsUpdate>({ daily_enabled: false, push_time: "", weekdays: [] });
let requestId = 0;
let viewActive = false;

function applySettings(data: DingTalkSettings): void {
  settings.value = data;
  form.daily_enabled = data.daily_enabled;
  form.push_time = data.push_time;
  form.weekdays = [...data.weekdays];
}

function isCurrent(id: number): boolean {
  return viewActive && id === requestId;
}

async function loadSettings(): Promise<void> {
  const id = ++requestId;
  loading.value = true;
  loadError.value = "";
  try {
    const data = await getDingTalkSettings();
    if (isCurrent(id)) applySettings(data);
  } catch (error) {
    if (isCurrent(id)) loadError.value = getErrorMessage(error);
  } finally {
    if (id === requestId) loading.value = false;
  }
}

function runStatus(last: DingTalkLastRun | null): DingTalkRunStatus | null {
  if (!last) return null;
  if (last.status === "success") return "success";
  if (last.status === "failed") return "failed";
  return "sending";
}

function statusLabel(status: DingTalkRunStatus | null): string {
  if (!status) return "暂无记录";
  if (status === "success") return "发送成功";
  if (status === "failed") return "发送失败";
  return "发送中";
}

function statusTone(status: DingTalkRunStatus | null): DingTalkTone {
  if (!status) return "lavender";
  if (status === "success") return "mint";
  if (status === "failed") return "peach";
  return "butter";
}

function statusIcon(status: DingTalkRunStatus | null): IconName {
  if (!status) return "rotateCcw";
  if (status === "success") return "checkCircle";
  if (status === "failed") return "alertCircle";
  return "rotateCcw";
}

function dateTime(value: string | null | undefined): string {
  return value ? formatBeijingDateTime(value) : "—";
}

const lastRun = computed(() => settings.value?.last_run ?? null);
const lastRunStatus = computed(() => runStatus(lastRun.value));
const lastRunLabel = computed(() => statusLabel(lastRunStatus.value));
const lastRunTone = computed(() => statusTone(lastRunStatus.value));

const summaryCards = computed<SummaryCard[]>(() => {
  const data = settings.value;
  if (!data) return [];
  return [
    {
      icon: "dingtalk",
      label: "机器人连接",
      value: data.configured ? "已配置" : "未配置",
      note: data.configured ? "Webhook 凭据就绪" : "需在服务器 .env 配置",
      tone: data.configured ? "mint" : "peach",
      badge: data.configured ? "就绪" : "未就绪",
    },
    {
      icon: "clock",
      label: "每日汇总计划",
      value: data.daily_enabled ? "已启用" : "已停用",
      note: data.daily_enabled ? "定时推送昨日业务明细" : "定时任务已暂停",
      tone: data.daily_enabled ? "azure" : "lavender",
      badge: data.daily_enabled ? "运行中" : "已暂停",
    },
    {
      icon: "calendar",
      label: "下次预计推送",
      value: data.next_push_at ? formatBeijingDateTime(data.next_push_at) : "—",
      note: data.next_push_at ? "按北京时间准时触发" : "未开启或未设排期",
      tone: "azure",
    },
    {
      icon: statusIcon(lastRunStatus.value),
      label: "最近一次推送",
      value: lastRunLabel.value,
      note: lastRun.value?.sent_at
        ? `已于 ${formatBeijingDateTime(lastRun.value.sent_at)} 投递`
        : lastRun.value?.error ? "投递异常" : "等待下一次触发",
      tone: statusTone(lastRunStatus.value),
      badge: lastRun.value?.stats_date ? `统计 ${lastRun.value.stats_date}` : undefined,
    },
  ];
});

function validationError(text: string): null {
  saveError.value = text;
  message.error(text);
  return null;
}

function payload(): DingTalkSettingsUpdate | null {
  const pushTime = form.push_time.trim();
  const selectedWeekdays = [...new Set(form.weekdays.map(Number))].sort((a, b) => a - b);
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(pushTime)) {
    return validationError("钉钉推送时间或星期无效");
  }
  if (selectedWeekdays.some((value) => !Number.isInteger(value) || value < 1 || value > 7)) {
    return validationError("钉钉推送星期无效");
  }
  if (form.daily_enabled && !selectedWeekdays.length) {
    return validationError("启用昨日汇总时至少选择一天");
  }
  return { daily_enabled: form.daily_enabled, push_time: pushTime, weekdays: selectedWeekdays };
}

async function saveSettings(): Promise<void> {
  if (saving.value) return;
  const next = payload();
  if (!next) return;
  const id = ++requestId;
  saving.value = true;
  saveError.value = "";
  try {
    await updateDingTalkSettings(next);
    if (!isCurrent(id)) return;
    message.success("推送计划已保存");
    await loadSettings();
  } catch (error) {
    if (isCurrent(id)) {
      saveError.value = getErrorMessage(error);
      message.error(saveError.value);
    }
  } finally {
    if (viewActive) saving.value = false;
  }
}

onMounted(() => {
  viewActive = true;
  void loadSettings();
});

onBeforeUnmount(() => {
  viewActive = false;
  requestId += 1;
});
</script>

<template>
  <section class="dingtalk-view">
    <div v-if="loading && !settings" class="analytics-kpi-grid" aria-busy="true">
      <NCard v-for="i in 4" :key="i" :bordered="false" class="analytics-kpi-card">
        <NSkeleton text width="55%" />
        <NSkeleton text width="72%" class="kpi-skeleton-value" />
        <NSkeleton text width="42%" />
      </NCard>
    </div>

    <NAlert v-if="loadError" type="error" class="dingtalk-error" title="钉钉设置加载失败">
      <div class="dingtalk-error-content">
        <span>{{ loadError }}</span>
        <NButton size="small" :disabled="loading" @click="loadSettings">重试</NButton>
      </div>
    </NAlert>

    <template v-if="settings">
      <div v-if="loading" class="dingtalk-refreshing" role="status"><NSpin size="small" />正在更新钉钉设置…</div>

      <div class="analytics-kpi-grid dingtalk-summary">
        <NCard
          v-for="card in summaryCards"
          :key="card.label"
          :bordered="false"
          class="analytics-kpi-card"
          :class="`tone-${card.tone}`"
        >
          <div class="analytics-kpi-head">
            <span>{{ card.label }} <NTag v-if="card.badge" size="small" round :bordered="false" type="default">{{ card.badge }}</NTag></span>
            <span class="analytics-icon-badge tone-badge"><morph-icon :icon="card.icon" size="18" stroke-width="1.8" /></span>
          </div>
          <strong class="analytics-kpi-value tone-value">{{ card.value }}</strong>
          <small>{{ card.note }}</small>
        </NCard>
      </div>

      <div class="dingtalk-dual-grid">
        <NCard :bordered="false" class="analytics-table-card">
          <template #header>
            <div class="analytics-panel-heading dingtalk-panel-heading">
              <div>
                <h2><morph-icon icon="clock" size="18" stroke-width="1.8" />推送计划与调度</h2>
                <span>定时按北京时间汇总昨日取消与退货订单并推送到钉钉群</span>
              </div>
            </div>
          </template>

          <NAlert type="info" :bordered="false" class="dingtalk-security-banner">
            同步失败告警为系统级风险通知，不受每日汇总开关影响；Webhook 与 Secret 凭据由服务器 <code>.env</code> 统一管理。
          </NAlert>

          <form class="dingtalk-form" @submit.prevent="saveSettings">
            <div class="dingtalk-toggle-row">
              <span class="dingtalk-toggle-label">
                <strong>启用昨日取消与退货订单汇总</strong>
                <small>定时汇总昨日 00:00 - 24:00 (北京时间) 的已发货取消与退货明细</small>
              </span>
              <NSwitch v-model:value="form.daily_enabled" aria-label="启用昨日取消与退货订单汇总" />
            </div>

            <div class="dingtalk-schedule-fields">
              <label class="dingtalk-time-field">
                <span>推送时间 (北京时间)</span>
                <input
                  v-model="form.push_time"
                  class="dingtalk-time-input"
                  type="time"
                  step="60"
                  required
                  aria-label="推送时间（北京时间）"
                />
              </label>

              <fieldset class="dingtalk-week-field">
                <legend>推送星期</legend>
                <NCheckboxGroup v-model:value="form.weekdays" aria-label="推送星期选择">
                  <div class="dingtalk-weekdays">
                    <NCheckbox v-for="weekday in weekdays" :key="weekday.value" :value="weekday.value">
                      {{ weekday.label }}
                    </NCheckbox>
                  </div>
                </NCheckboxGroup>
              </fieldset>
            </div>

            <NAlert v-if="saveError" type="error" :bordered="false" class="dingtalk-save-error" title="推送计划保存失败">
              {{ saveError }}
            </NAlert>

            <div class="dingtalk-actions">
              <NButton type="primary" attr-type="submit" :loading="saving" :disabled="saving">
                <template #icon><morph-icon icon="check" size="14" stroke-width="2" /></template>
                保存设置
              </NButton>
            </div>
          </form>
        </NCard>

        <NCard :bordered="false" class="analytics-table-card">
          <template #header>
            <div class="analytics-panel-heading dingtalk-panel-heading">
              <div>
                <h2><morph-icon icon="rotateCcw" size="18" stroke-width="1.8" />最近一次汇总投递</h2>
                <span>展示最近一次正式定时推送的执行记录与投递结果</span>
              </div>
            </div>
          </template>

          <dl class="dingtalk-last-grid">
            <div class="dingtalk-fact-item">
              <dt>统计业务日期</dt>
              <dd><strong>{{ lastRun?.stats_date || "—" }}</strong></dd>
            </div>
            <div class="dingtalk-fact-item">
              <dt>投递执行状态</dt>
              <dd><NTag size="small" round :bordered="false" :class="`dingtalk-tone-tag--${lastRunTone}`">{{ lastRunLabel }}</NTag></dd>
            </div>
            <div class="dingtalk-fact-item">
              <dt>实际发送时间</dt>
              <dd><strong>{{ dateTime(lastRun?.sent_at) }}</strong></dd>
            </div>
            <div class="dingtalk-fact-item">
              <dt>失败原因 / 详情</dt>
              <dd :class="{ 'dingtalk-error-text': Boolean(lastRun?.error) }"><strong>{{ lastRun?.error || "无异常" }}</strong></dd>
            </div>
          </dl>

          <div class="dingtalk-spec-card">
            <div class="dingtalk-spec-head">
              <morph-icon icon="layers" size="14" stroke-width="1.8" />
              <strong>推送规范与数据口径</strong>
            </div>
            <ul class="dingtalk-spec-list">
              <li><b>统计范围</b>：仅统计昨日已发货取消件与各类退货记录，按北京时间自然日归组。</li>
              <li><b>店铺隔离</b>：独立输出各店铺不同履约渠道 (FBP / realFBS / WHD) 的订单量与明细。</li>
              <li><b>隐私保护</b>：敏感买家留言与客户个人信息已被过滤脱敏，聚合展示官方原因。</li>
            </ul>
          </div>
        </NCard>
      </div>
    </template>
  </section>
</template>
