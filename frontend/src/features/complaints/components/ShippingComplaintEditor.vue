<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { NButton, NInput, NModal, NSelect, useMessage } from "naive-ui";
import { getErrorMessage } from "../../../shared/api/client";
import { saveShippingComplaint, type ShippingComplaintPayload } from "../api";
import type { ComplaintRecord, ShippingComplaintOrder } from "../types";
import type { ShopId } from "../../../shared/types/common";
import ComplaintCompensationFields from "./ComplaintCompensationFields.vue";
import MorphIcon from "../../../shared/components/MorphIcon.vue";
import {
  beijingInputToUtc,
  booleanOptions,
  boolChoice,
  compensationPreview,
  deadlineText,
  formatBeijingDateTimeInput,
  nullableBool,
  numberOrNull,
  type BoolChoice,
} from "./editor";

type ShippingComplaintForm = {
  shopId: ShopId;
  postingNumber: string;
  complaintNumber: string;
  complaintAt: string;
  channel: string;
  warehouse: string;
  orderProcessStatus: string;
  complaintStatus: string;
  compensationStatus: string;
  platformCompensation: number | null;
  platformAt: string;
  logisticsCompensation: number | null;
  logisticsAt: string;
  notReceivedReturn: BoolChoice;
  resolved: BoolChoice;
  notes: string;
};

const props = defineProps<{
  row: ShippingComplaintOrder | null;
  complaint: ComplaintRecord | null;
}>();
const emit = defineEmits<{ saved: [] }>();
const show = defineModel<boolean>("show", { required: true });
const message = useMessage();
const saving = ref(false);
const form = reactive<ShippingComplaintForm>({
  shopId: 1,
  postingNumber: "",
  complaintNumber: "",
  complaintAt: "",
  channel: "",
  warehouse: "",
  orderProcessStatus: "",
  complaintStatus: "",
  compensationStatus: "",
  platformCompensation: null,
  platformAt: "",
  logisticsCompensation: null,
  logisticsAt: "",
  notReceivedReturn: "",
  resolved: "",
  notes: "",
});
let saveId = 0;
let mounted = false;

const platformConversion = computed(() => compensationPreview(
  form.platformCompensation,
  form.platformAt,
  props.complaint?.platform_compensation_rub,
  props.complaint?.platform_compensated_at,
  props.complaint?.platform_compensation_missing_rate,
  props.complaint?.platform_compensation_converted_currency,
  props.complaint?.platform_compensation_converted_amount,
  props.complaint?.platform_compensation_service_penalty_exchange_rates,
  "RUB",
));
const logisticsConversion = computed(() => compensationPreview(
  form.logisticsCompensation,
  form.logisticsAt,
  props.complaint?.logistics_compensation_cny,
  props.complaint?.logistics_compensated_at,
  props.complaint?.logistics_compensation_missing_rate,
  props.complaint?.logistics_compensation_converted_currency,
  props.complaint?.logistics_compensation_converted_amount,
  props.complaint?.logistics_compensation_service_penalty_exchange_rates,
  "CNY",
));

watch([show, () => props.row, () => props.complaint], () => {
  if (!show.value || !props.row) return;
  const complaint = props.complaint;
  Object.assign(form, {
    shopId: props.row.shop_id,
    postingNumber: props.row.posting_number,
    complaintNumber: complaint?.complaint_number || "",
    complaintAt: formatBeijingDateTimeInput(complaint?.complaint_at) || formatBeijingDateTimeInput(new Date()),
    channel: complaint?.channel || "",
    warehouse: complaint?.warehouse || "",
    orderProcessStatus: complaint?.order_process_status || "",
    complaintStatus: complaint?.complaint_status || "",
    compensationStatus: complaint?.compensation_status || "",
    platformCompensation: numberOrNull(complaint?.platform_compensation_rub),
    platformAt: formatBeijingDateTimeInput(complaint?.platform_compensated_at),
    logisticsCompensation: numberOrNull(complaint?.logistics_compensation_cny),
    logisticsAt: formatBeijingDateTimeInput(complaint?.logistics_compensated_at),
    notReceivedReturn: boolChoice(complaint?.not_received_return),
    resolved: boolChoice(complaint?.resolved),
    notes: complaint?.notes || "",
  });
}, { immediate: true });

async function submit(): Promise<void> {
  if (saving.value) return;
  if (!form.complaintNumber.trim() || !form.complaintAt || !form.channel.trim()) {
    message.error("投诉编号、投诉时间和投诉渠道为必填项");
    return;
  }
  const currentSave = ++saveId;
  saving.value = true;
  const body: ShippingComplaintPayload = {
    shop_id: form.shopId,
    posting_number: form.postingNumber,
    complaint_number: form.complaintNumber.trim(),
    complaint_at: beijingInputToUtc(form.complaintAt),
    channel: form.channel.trim(),
    not_received_return: nullableBool(form.notReceivedReturn),
    warehouse: form.warehouse.trim(),
    order_process_status: form.orderProcessStatus.trim(),
    complaint_status: form.complaintStatus.trim(),
    compensation_status: form.compensationStatus.trim(),
    platform_compensation_rub: form.platformCompensation,
    platform_compensated_at: beijingInputToUtc(form.platformAt),
    logistics_compensation_cny: form.logisticsCompensation,
    logistics_compensated_at: beijingInputToUtc(form.logisticsAt),
    resolved: nullableBool(form.resolved),
    package_returned: null,
    notes: form.notes,
  };
  try {
    await saveShippingComplaint(body);
    if (currentSave !== saveId || !mounted) return;
    message.success("投诉已保存");
    show.value = false;
    emit("saved");
  } catch (cause) {
    if (currentSave === saveId && mounted) message.error(getErrorMessage(cause));
  } finally {
    if (currentSave === saveId) saving.value = false;
  }
}

onMounted(() => { mounted = true; });
onBeforeUnmount(() => {
  mounted = false;
  saveId += 1;
});
</script>

<template>
  <NModal v-model:show="show" preset="card" class="complaints-modal" :style="{ width: 'min(720px, 92vw)' }" :mask-closable="!saving" :title="complaint ? `编辑投诉 ${complaint.complaint_number}` : `为 ${row?.posting_number || ''} 新建投诉`">
    <p class="complaints-modal-subtitle">投诉编号、投诉时间和投诉渠道为必填项</p>
    <form class="complaints-form" @submit.prevent="submit">
      <div class="complaints-form-grid">
        <label class="complaints-field">投诉编号<NInput v-model:value="form.complaintNumber" :readonly="Boolean(complaint)" /></label>
        <label class="complaints-field">投诉时间<input v-model="form.complaintAt" class="complaints-native-input" type="datetime-local" required /></label>
        <label class="complaints-field">投诉渠道<NInput v-model:value="form.channel" placeholder="如：Ozon Support / 官方工单" /></label>
        <div class="complaints-field"><span>固定投诉截止日期</span><div class="complaints-readonly-field">{{ row ? deadlineText(row) : "—" }}</div></div>
        <label class="complaints-field">所在仓库<NInput v-model:value="form.warehouse" placeholder="如：中国前置仓 / 本地仓" /></label>
        <label class="complaints-field">订单处理状态<NInput v-model:value="form.orderProcessStatus" placeholder="如：已核实 / 待处理" /></label>
        <label class="complaints-field">投诉状态<NInput v-model:value="form.complaintStatus" placeholder="如：已受理 / 平台审核中" /></label>
        <label class="complaints-field">赔付状态<NInput v-model:value="form.compensationStatus" placeholder="如：已批准 / 待打款" /></label>
        <ComplaintCompensationFields v-model:amount="form.platformCompensation" v-model:at="form.platformAt" title="Ozon 平台赔偿" currency="RUB" :preview="platformConversion" />
        <ComplaintCompensationFields v-model:amount="form.logisticsCompensation" v-model:at="form.logisticsAt" title="物流商赔偿" currency="CNY" :preview="logisticsConversion" />
        <label class="complaints-field">未收到退件<NSelect v-model:value="form.notReceivedReturn" :options="booleanOptions" /></label>
        <label class="complaints-field">是否完结<NSelect v-model:value="form.resolved" :options="booleanOptions" /></label>
        <label class="complaints-field complaints-notes">备注<NInput v-model:value="form.notes" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写处理备注…" /></label>
      </div>
      <div class="complaints-form-actions">
        <NButton type="primary" attr-type="submit" :loading="saving"><template #icon><MorphIcon icon="check" size="14" stroke-width="2" /></template>保存</NButton>
        <NButton attr-type="button" :disabled="saving" @click="show = false">取消</NButton>
      </div>
    </form>
  </NModal>
</template>
