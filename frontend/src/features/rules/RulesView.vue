<script setup lang="ts">
import "./rules.css";
import { computed, h, onMounted, ref } from "vue";
import MorphIcon from "../../shared/components/MorphIcon.vue";
import type { IconName } from "../../shared/icons/tabler";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NInput,
  NSelect,
  NSpin,
  NTag,
  useMessage,
} from "naive-ui";
import EmptyState from "../../shared/components/EmptyState.vue";
import type { DataTableColumns } from "naive-ui";
import { deleteShortName, dissolveMergeGroup, getProductRules, saveMergeGroup, saveShortName } from "./api";
import { getErrorMessage } from "../../shared/api/client";
import { copyText } from "../../shared/utils/clipboard";
import { formatBeijingDateTime, formatInteger } from "../../shared/utils/format";
import type {
  ProductRuleGroup,
  ProductRuleMember,
  ProductRuleMemberType,
  ProductShortName,
  ProductRulesResponse,
} from "./types";

type SummaryTone = "azure" | "mint" | "peach" | "lavender";
type SummaryCard = {
  icon: IconName;
  label: string;
  badge: string;
  value: number;
  unit: string;
  note: string;
  tone: SummaryTone;
};

const message = useMessage();
const rulesData = ref<ProductRulesResponse | null>(null);
const loading = ref(false);
const loadError = ref("");
const searchDraft = ref("");
const search = ref("");
const shortSku = ref("");
const shortName = ref("");
const savingShortName = ref(false);
const deletingShortSku = ref("");
const editingGroupId = ref<number | null>(null);
const primaryOffer = ref("");
const primarySku = ref("");
const members = ref<ProductRuleMember[]>([newMember()]);
const savingMerge = ref(false);
const dissolvingGroupId = ref<number | null>(null);
let rulesRequestId = 0;

const memberTypeOptions: Array<{ label: string; value: ProductRuleMemberType }> = [
  { label: "SKU", value: "sku" },
  { label: "货号", value: "offer_id" },
];

const summaryCards = computed<SummaryCard[]>(() => {
  const data = rulesData.value;
  if (!data) return [];
  const conflicts = data.conflicts.length;
  return [
    {
      icon: "tag",
      label: "中文短名称规则",
      badge: "SKU 映射",
      value: data.summary.short_names,
      unit: "条规则",
      note: "用于全系统报表统一商品简称",
      tone: "mint",
    },
    {
      icon: "gitMerge",
      label: "全局合并关系",
      badge: "主货号聚合",
      value: data.summary.merges,
      unit: "个主货号",
      note: "多规格/多店铺货号归一聚合分析",
      tone: "azure",
    },
    {
      icon: conflicts ? "alertTriangle" : "check",
      label: "待处理旧冲突",
      badge: conflicts ? "需处理" : "正常",
      value: conflicts,
      unit: "项冲突",
      note: conflicts ? "存在旧规则或未确认合并冲突" : "所有商品合并关系正常生效",
      tone: conflicts ? "peach" : "mint",
    },
    {
      icon: "layers",
      label: "内置清洗规则",
      badge: "系统清洗",
      value: 1,
      unit: "项规则",
      note: data.fixed_rule,
      tone: "lavender",
    },
  ];
});

const shortNameColumns: DataTableColumns<ProductShortName> = [
  {
    key: "sku",
    title: "SKU",
    minWidth: 200,
    render: (row) => h("button", {
      type: "button",
      class: "rules-copy-button",
      title: "点击复制 SKU",
      onClick: () => { void copySku(row.sku); },
    }, [
      h(MorphIcon, { icon: "copy", size: "12", strokeWidth: "2" }),
      h("strong", row.sku),
    ]),
  },
  {
    key: "short_name",
    title: "中文短名称",
    minWidth: 220,
    render: (row) => h("span", { class: "rules-short-name" }, row.short_name),
  },
  {
    key: "updated_at",
    title: "更新时间",
    width: 170,
    align: "right",
    render: (row) => h("span", { class: "rules-time" }, formatBeijingDateTime(row.updated_at)),
  },
  {
    key: "actions",
    title: "操作",
    width: 170,
    align: "right",
    render: (row) => h("div", { class: "rules-table-actions" }, [
      h(NButton, {
        size: "small",
        text: true,
        type: "primary",
        disabled: Boolean(deletingShortSku.value),
        onClick: () => editShortName(row),
      }, { default: () => [h(MorphIcon, { icon: "edit", size: "12", strokeWidth: "2" }), "编辑"] }),
      h(NButton, {
        size: "small",
        text: true,
        type: "error",
        loading: deletingShortSku.value === row.sku,
        disabled: Boolean(deletingShortSku.value && deletingShortSku.value !== row.sku),
        onClick: () => { void removeShortName(row.sku); },
      }, { default: () => [h(MorphIcon, { icon: "trash", size: "12", strokeWidth: "2" }), "删除"] }),
    ]),
  },
];

function newMember(): ProductRuleMember {
  return { key_type: "sku", key_value: "" };
}

async function loadRules(query = search.value): Promise<void> {
  const requestId = ++rulesRequestId;
  loading.value = true;
  loadError.value = "";
  try {
    const data = await getProductRules(query);
    if (requestId === rulesRequestId) rulesData.value = data;
  } catch (error) {
    if (requestId === rulesRequestId) loadError.value = getErrorMessage(error);
  } finally {
    if (requestId === rulesRequestId) loading.value = false;
  }
}

function submitSearch(): void {
  search.value = searchDraft.value.trim();
  void loadRules(search.value);
}

function clearSearch(): void {
  searchDraft.value = "";
  search.value = "";
  void loadRules("");
}

function resetShortForm(): void {
  shortSku.value = "";
  shortName.value = "";
}

async function submitShortName(): Promise<void> {
  const sku = shortSku.value.trim();
  const name = shortName.value.trim();
  if (!sku) {
    message.error("请输入 SKU");
    return;
  }
  if (!name) {
    message.error("请输入中文短名称");
    return;
  }
  savingShortName.value = true;
  try {
    await saveShortName(sku, name);
  } catch (error) {
    message.error(getErrorMessage(error));
    return;
  } finally {
    savingShortName.value = false;
  }
  message.success("短名称已保存");
  resetShortForm();
  await loadRules(search.value);
}

function editShortName(row: ProductShortName): void {
  shortSku.value = row.sku;
  shortName.value = row.short_name;
}

async function removeShortName(sku: string): Promise<void> {
  deletingShortSku.value = sku;
  try {
    await deleteShortName(sku);
  } catch (error) {
    message.error(getErrorMessage(error));
    return;
  } finally {
    deletingShortSku.value = "";
  }
  message.success("短名称已删除");
  await loadRules(search.value);
}

async function copySku(sku: string): Promise<void> {
  try {
    await copyText(sku);
    message.success("SKU 已复制");
  } catch (error) {
    message.error(getErrorMessage(error));
  }
}

function resetMergeForm(): void {
  editingGroupId.value = null;
  primaryOffer.value = "";
  primarySku.value = "";
  members.value = [newMember()];
}

function addMember(): void {
  members.value.push(newMember());
}

function removeMember(index: number): void {
  members.value.splice(index, 1);
}

function setMemberType(member: ProductRuleMember, value: string | number | null): void {
  if (value === "sku" || value === "offer_id") member.key_type = value;
}

function editGroup(group: ProductRuleGroup): void {
  editingGroupId.value = group.id;
  primaryOffer.value = group.primary_offer_id ?? "";
  primarySku.value = group.primary_sku ?? "";
  const editableMembers = group.members
    .filter((member) => !(member.key_type === "offer_id" && member.key_value === group.primary_offer_id))
    .map((member) => ({ ...member }));
  members.value = editableMembers.length ? editableMembers : [newMember()];
}

async function submitMerge(): Promise<void> {
  const primary = primaryOffer.value.trim();
  const mergeMembers = members.value
    .map((member) => ({ key_type: member.key_type, key_value: member.key_value.trim() }))
    .filter((member) => member.key_value);
  if (!primary) {
    message.error("请输入主货号");
    return;
  }
  if (!mergeMembers.length) {
    message.error("请至少添加一个合并成员");
    return;
  }
  savingMerge.value = true;
  try {
    await saveMergeGroup({
      kind: "merge",
      id: editingGroupId.value ?? 0,
      primary_offer_id: primary,
      primary_sku: primarySku.value.trim(),
      members: mergeMembers,
    });
  } catch (error) {
    message.error(getErrorMessage(error));
    return;
  } finally {
    savingMerge.value = false;
  }
  message.success(editingGroupId.value ? "合并关系已更新" : "全局合并已保存");
  resetMergeForm();
  await loadRules(search.value);
}

async function dissolveGroup(id: number): Promise<void> {
  dissolvingGroupId.value = id;
  try {
    await dissolveMergeGroup(id);
  } catch (error) {
    message.error(getErrorMessage(error));
    return;
  } finally {
    dissolvingGroupId.value = null;
  }
  message.success("合并关系已解散");
  resetMergeForm();
  await loadRules(search.value);
}

function groupFoot(group: ProductRuleGroup): string {
  return group.note || `更新于 ${formatBeijingDateTime(group.updated_at)}`;
}

onMounted(() => { void loadRules(); });
</script>

<template>
  <section class="rules-view">
    <div v-if="!rulesData && loading" class="rules-loading">
      <NSpin size="medium" />
      <span>正在读取商品匹配规则…</span>
    </div>

    <NAlert v-if="loadError" type="error" class="rules-error" :title="loadError">
      <div class="rules-error-content">
        <span>商品匹配规则未更新，请重试。</span>
        <NButton size="small" @click="loadRules(search)">重试</NButton>
      </div>
    </NAlert>

    <template v-if="rulesData">
      <div v-if="loading" class="rules-refreshing" role="status">
        <NSpin size="small" /> 正在更新规则…
      </div>

      <div class="rules-summary">
        <NCard
          v-for="card in summaryCards"
          :key="card.label"
          :bordered="false"
          class="rules-summary-card"
          :class="`tone-${card.tone}`"
        >
          <div class="rules-summary-head">
            <span>{{ card.label }} <NTag size="small" round :bordered="false" type="default">{{ card.badge }}</NTag></span>
            <span class="rules-summary-icon tone-badge"><morph-icon :icon="card.icon" size="18" stroke-width="1.8" /></span>
          </div>
          <strong class="tone-value">{{ formatInteger(card.value) }}<small>{{ card.unit }}</small></strong>
          <small>{{ card.note }}</small>
        </NCard>
      </div>

      <div class="rules-grid">
        <NCard :bordered="false" class="rules-panel">
          <template #header>
            <div class="rules-panel-heading">
              <div>
                <h2><morph-icon icon="tag" size="18" stroke-width="1.8" />中文短名称规则</h2>
                <span>按 SKU 精准匹配并在全系统报表中展示</span>
              </div>
              <NTag size="small" round :bordered="false" type="default">
                <morph-icon icon="layers" size="12" stroke-width="2" />{{ rulesData.fixed_rule }}
              </NTag>
            </div>
          </template>

          <form class="rules-form" @submit.prevent="submitShortName">
            <div class="rules-fields-grid">
              <label class="rules-field">
                <span>商品 SKU</span>
                <NInput v-model:value="shortSku" placeholder="输入完整 SKU 编码" autocomplete="off" />
              </label>
              <label class="rules-field">
                <span>中文短名称</span>
                <NInput v-model:value="shortName" placeholder="如：Xiaomi Tag 智能追踪器" autocomplete="off" />
              </label>
            </div>
            <div class="rules-form-actions">
              <NButton type="primary" attr-type="submit" :loading="savingShortName">
                <template #icon><morph-icon icon="plus" size="14" stroke-width="2" /></template>
                保存规则
              </NButton>
              <NButton attr-type="button" :disabled="savingShortName" @click="resetShortForm">重置</NButton>
            </div>
          </form>

          <form class="rules-search" role="search" @submit.prevent="submitSearch">
            <NInput v-model:value="searchDraft" type="text" aria-label="搜索短名称规则" placeholder="搜索 SKU 或中文短名称…">
              <template #prefix><morph-icon icon="search" size="15" stroke-width="1.8" /></template>
            </NInput>
            <NButton type="primary" attr-type="submit" :loading="loading">
              <template #icon><morph-icon icon="search" size="14" stroke-width="2" /></template>
              查询
            </NButton>
            <NButton attr-type="button" @click="clearSearch">清除</NButton>
          </form>

          <NDataTable
            class="rules-table"
            :columns="shortNameColumns"
            :data="rulesData.short_names"
            :loading="loading"
            :pagination="false"
            :scroll-x="720"
          >
            <template #empty>
              <EmptyState :title="loadError ? '短名称规则加载失败' : '暂无短名称规则'" :hint="loadError ? undefined : '在上方输入 SKU 和中文短名称即可添加'" />
            </template>
          </NDataTable>
        </NCard>

        <NCard :bordered="false" class="rules-panel">
          <template #header>
            <div class="rules-panel-heading">
              <div>
                <h2><morph-icon icon="gitMerge" size="18" stroke-width="1.8" />SKU / 货号全局合并</h2>
                <span>主货号作为全局聚合的唯一分析身份</span>
              </div>
              <NTag v-if="editingGroupId !== null" size="small" round type="info">编辑中</NTag>
            </div>
          </template>

          <form class="rules-form" @submit.prevent="submitMerge">
            <div class="rules-fields-grid">
              <label class="rules-field">
                <span>主货号 (Primary Offer ID)</span>
                <NInput v-model:value="primaryOffer" placeholder="输入主货号" autocomplete="off" />
              </label>
              <label class="rules-field">
                <span>名称解析 SKU (可选)</span>
                <NInput v-model:value="primarySku" placeholder="仅主货号对应多 SKU 时需填写" autocomplete="off" />
              </label>
            </div>
            <div class="rules-members-section">
              <div class="rules-members-head">
                <strong>关联成员列表</strong>
                <NButton size="small" quaternary attr-type="button" @click="addMember">
                  <template #icon><morph-icon icon="plus" size="13" stroke-width="2.2" /></template>
                  增加成员
                </NButton>
              </div>
              <div class="rules-members">
                <div v-for="(member, index) in members" :key="index" class="rules-member">
                  <NSelect
                    :value="member.key_type"
                    :options="memberTypeOptions"
                    aria-label="成员类型"
                    class="rules-member-type"
                    @update:value="setMemberType(member, $event)"
                  />
                  <NInput v-model:value="member.key_value" placeholder="输入关联 SKU 或货号" aria-label="成员值" autocomplete="off" />
                  <NButton
                    size="small"
                    quaternary
                    circle
                    attr-type="button"
                    aria-label="删除成员"
                    :disabled="savingMerge"
                    @click="removeMember(index)"
                  >
                    <template #icon><morph-icon icon="x" size="14" stroke-width="2" /></template>
                  </NButton>
                </div>
              </div>
            </div>
            <div class="rules-form-actions">
              <NButton type="primary" attr-type="submit" :loading="savingMerge">
                <template #icon><morph-icon icon="check" size="14" stroke-width="2" /></template>
                {{ editingGroupId === null ? "保存合并关系" : "更新合并关系" }}
              </NButton>
              <NButton attr-type="button" :disabled="savingMerge" @click="resetMergeForm">重置</NButton>
            </div>
          </form>

          <div v-if="rulesData.groups.length" class="rules-group-list">
            <article
              v-for="group in rulesData.groups"
              :key="group.id"
              class="rules-group-card"
              :class="{ 'is-pending': group.status !== 'active' }"
            >
              <div class="rules-group-head">
                <div class="rules-primary-chip">
                  <morph-icon icon="box" size="12" stroke-width="2" />
                  <span>主货号 · {{ group.primary_offer_id || "待设置" }}</span>
                </div>
                <NTag size="small" round :bordered="false" :type="group.status === 'active' ? 'success' : 'warning'">
                  {{ group.status === "active" ? "生效" : "待处理" }}
                </NTag>
              </div>
              <strong class="rules-product-name">{{ group.product_name }}</strong>
              <div class="rules-tags">
                <NTag
                  v-for="member in group.members"
                  :key="`${member.key_type}:${member.key_value}`"
                  size="small"
                  :type="member.key_type === 'sku' ? 'default' : 'info'"
                >
                  {{ member.key_type === "sku" ? "SKU" : "货号" }} · {{ member.key_value }}
                </NTag>
              </div>
              <div class="rules-group-foot">
                <small>{{ groupFoot(group) }}</small>
                <div class="rules-table-actions">
                  <NButton size="small" text type="primary" @click="editGroup(group)">
                    <template #icon><morph-icon icon="edit" size="12" stroke-width="2" /></template>
                    编辑
                  </NButton>
                  <NButton
                    size="small"
                    text
                    type="error"
                    :loading="dissolvingGroupId === group.id"
                    :disabled="dissolvingGroupId !== null && dissolvingGroupId !== group.id"
                    @click="dissolveGroup(group.id)"
                  >
                    <template #icon><morph-icon icon="trash" size="12" stroke-width="2" /></template>
                    解散
                  </NButton>
                </div>
              </div>
            </article>
          </div>
          <EmptyState v-else title="暂无全局合并关系" hint="在上方添加主货号与关联成员即可建立全局合并分析身份" />
        </NCard>
      </div>

      <section v-if="rulesData.conflicts.length" class="rules-conflicts">
        <div class="rules-conflicts-head">
          <morph-icon icon="alertTriangle" size="18" stroke-width="2" />
          <h2>待处理的旧规则冲突 ({{ rulesData.conflicts.length }})</h2>
        </div>
        <div class="rules-conflicts-list">
          <div v-for="conflict in rulesData.conflicts" :key="`${conflict.key_type}:${conflict.key_value}`" class="rules-conflict-item">
            <strong>{{ conflict.key_value }}</strong>
            <span>{{ conflict.note }}</span>
          </div>
        </div>
      </section>
    </template>
  </section>
</template>
