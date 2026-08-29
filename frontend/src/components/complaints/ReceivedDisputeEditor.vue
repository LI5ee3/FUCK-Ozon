<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { NButton, NInput, NInputNumber, NModal, NSelect, useMessage } from "naive-ui";
import { getErrorMessage } from "../../api/client";
import { saveReceivedDispute, type ReceivedDisputePayload } from "../../api/complaints";
import type { ReceivedDisputeRecord, ShopId } from "../../types/api";
import ComplaintCompensationFields from "../ComplaintCompensationFields.vue";
import MorphIcon from "../MorphIcon.vue";
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

type ReceivedDisputeForm = {
  shopId: ShopId;
  returnNumber: string;
  refundType: string;
  refundAmount: number | null;
  refundCurrency: string;
  platformCompensation: number | null;
  platformAt: string;
  logisticsCompensation: number | null;
  logisticsAt: string;
  processStatus: string;
  returnMethod: string;
  imlReturnNumber: string;
  imlSystemSn: string;
  buyerTrackingNumber: string;
  handlingMethod: string;
  videoRecorded: BoolChoice;
  outboundOrderNumber: string;
  returnResult: string;
  notes: string;
};

const props = defineProps<{ row: ReceivedDisputeRecord | null }>();
const emit = defineEmits<{ saved: [] }>();
const show = defineModel<boolean>("show", { required: true });
const message = useMessage();
const saving = ref(false);
const form = reactive<ReceivedDisputeForm>({
  shopId: 1,
  returnNumber: "",
  refundType: "",
  refundAmount: null,
  refundCurrency: "",
  platformCompensation: null,
  platformAt: "",
  logisticsCompensation: null,
  logisticsAt: "",
  processStatus: "",
  returnMethod: "",
  imlReturnNumber: "",
  imlSystemSn: "",
  buyerTrackingNumber: "",
  handlingMethod: "",
  videoRecorded: "",
  outboundOrderNumber: "",
  returnResult: "",
  notes: "",
});
let saveId = 0;
let mounted = false;

const refundTypeOptions = [
  { label: "未填写", value: "" },
  { label: "部分退款", value: "部分退款" },
  { label: "全额退款", value: "全额退款" },
  { label: "多次纠纷", value: "多次纠纷" },
];
const returnMethodOptions = [
  { label: "未填写", value: "" },
  { label: "未退货", value: "未退货" },
  { label: "IML", value: "IML" },
  { label: "FBO二次销售", value: "FBO二次销售" },
];
const handlingMethodOptions = [
  { label: "未填写", value: "" },
  { label: "退回", value: "退回" },
  { label: "销毁", value: "销毁" },
];
const returnResultOptions = [
  { label: "未填写", value: "" },
  { label: "退回国内中", value: "退回国内中" },
  { label: "已签收", value: "已签收" },
  { label: "已销毁", value: "已销毁" },
];

const platformConversion = computed(() => compensationPreview(
  form.platformCompensation,
  form.platformAt,
  props.row?.platform_compensation_rub,
  props.row?.platform_compensated_at,
  props.row?.platform_compensation_missing_rate,
  props.row?.platform_compensation_converted_currency,
  props.row?.platform_compensation_converted_amount,
  props.row?.platform_compensation_base_rates,
  "RUB",
));
const logisticsConversion = computed(() => compensationPreview(
  form.logisticsCompensation,
  form.logisticsAt,
  props.row?.logistics_compensation_cny,
  props.row?.logistics_compensated_at,
  props.row?.logistics_compensation_missing_rate,
  props.row?.logistics_compensation_converted_currency,
  props.row?.logistics_compensation_converted_amount,
  props.row?.logistics_compensation_base_rates,
  "CNY",
));

watch([show, () => props.row], () => {
  if (!show.value || !props.row) return;
  const row = props.row;
  Object.assign(form, {
    shopId: row.shop_id,
    returnNumber: row.return_number,
    refundType: row.refund_type || "",
    refundAmount: row.refund_amount,
    refundCurrency: row.refund_currency || row.settlement_currency,
    platformCompensation: numberOrNull(row.platform_compensation_rub),
    platformAt: formatBeijingDateTimeInput(row.platform_compensated_at),
    logisticsCompensation: numberOrNull(row.logistics_compensation_cny),
    logisticsAt: formatBeijingDateTimeInput(row.logistics_compensated_at),
    processStatus: row.process_status || "",
    returnMethod: row.return_method || "",
    imlReturnNumber: row.iml_return_number || "",
    imlSystemSn: row.iml_system_sn || "",
    buyerTrackingNumber: row.buyer_tracking_number || "",
    handlingMethod: row.handling_method || "",
    videoRecorded: boolChoice(row.video_recorded),
    outboundOrderNumber: row.outbound_order_number || "",
    returnResult: row.return_result || "",
    notes: row.notes || "",
  });
}, { immediate: true });

async function submit(): Promise<void> {
  if (saving.value) return;
  const currentSave = ++saveId;
  saving.value = true;
  const body: ReceivedDisputePayload = {
    shop_id: form.shopId,
    return_number: form.returnNumber,
    refund_type: form.refundType,
    refund_amount: form.refundAmount,
    refund_currency: form.refundCurrency.trim(),
    platform_compensation_rub: form.platformCompensation,
    platform_compensated_at: beijingInputToUtc(form.platformAt),
    logistics_compensation_cny: form.logisticsCompensation,
    logistics_compensated_at: beijingInputToUtc(form.logisticsAt),
    process_status: form.processStatus.trim(),
    return_method: form.returnMethod,
    iml_return_number: form.imlReturnNumber.trim(),
    iml_system_sn: form.imlSystemSn.trim(),
    buyer_tracking_number: form.buyerTrackingNumber.trim(),
    handling_method: form.handlingMethod,
    video_recorded: nullableBool(form.videoRecorded),
    outbound_order_number: form.outboundOrderNumber.trim(),
    return_result: form.returnResult,
    notes: form.notes,
  };
  try {
    await saveReceivedDispute(body);
    if (currentSave !== saveId || !mounted) return;
    message.success("已收货纠纷已保存");
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
  <NModal v-model:show="show" preset="card" class="complaints-modal" :style="{ width: 'min(720px, 92vw)' }" :mask-closable="!saving" title="编辑已收货纠纷">
    <p class="complaints-modal-subtitle">{{ row ? `${row.return_number} · ${row.shop_name}` : "请选择一条退货申请" }}</p>
    <form class="complaints-form" @submit.prevent="submit">
      <div class="complaints-form-grid">
        <div class="complaints-field"><span>固定投诉截止日期</span><div class="complaints-readonly-field">{{ row ? deadlineText(row) : "—" }}</div></div>
        <label class="complaints-field">是否退款<NSelect v-model:value="form.refundType" :options="refundTypeOptions" /></label>
        <label class="complaints-field">退款金额<NInputNumber v-model:value="form.refundAmount" :min="0" :precision="2" placeholder="0.00" /></label>
        <label class="complaints-field">退款币种<NInput v-model:value="form.refundCurrency" readonly /></label>
        <ComplaintCompensationFields v-model:amount="form.platformCompensation" v-model:at="form.platformAt" title="Ozon 平台赔偿" currency="RUB" :preview="platformConversion" />
        <ComplaintCompensationFields v-model:amount="form.logisticsCompensation" v-model:at="form.logisticsAt" title="物流商赔偿" currency="CNY" :preview="logisticsConversion" />
        <label class="complaints-field">处理状态<NInput v-model:value="form.processStatus" placeholder="如：处理中 / 待核实 / 已完结" /></label>
        <label class="complaints-field">退货方式<NSelect v-model:value="form.returnMethod" :options="returnMethodOptions" /></label>
        <label class="complaints-field">IML退货单号<NInput v-model:value="form.imlReturnNumber" placeholder="IML 单号" /></label>
        <label class="complaints-field">IML系统SN<NInput v-model:value="form.imlSystemSn" placeholder="IML 系统序列号" /></label>
        <label class="complaints-field">买家邮寄追踪号<NInput v-model:value="form.buyerTrackingNumber" placeholder="买家寄出物流单号" /></label>
        <label class="complaints-field">处理方式<NSelect v-model:value="form.handlingMethod" :options="handlingMethodOptions" /></label>
        <label class="complaints-field">是否拍视频<NSelect v-model:value="form.videoRecorded" :options="booleanOptions" /></label>
        <label class="complaints-field">出库订单编号<NInput v-model:value="form.outboundOrderNumber" placeholder="关联出库单号" /></label>
        <label class="complaints-field">退件结果<NSelect v-model:value="form.returnResult" :options="returnResultOptions" /></label>
        <label class="complaints-field complaints-notes">备注<NInput v-model:value="form.notes" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写纠纷备注…" /></label>
      </div>
      <div class="complaints-form-actions">
        <NButton type="primary" attr-type="submit" :loading="saving"><template #icon><MorphIcon icon="check" size="14" stroke-width="2" /></template>保存</NButton>
        <NButton attr-type="button" :disabled="saving" @click="show = false">取消</NButton>
      </div>
    </form>
  </NModal>
</template>
