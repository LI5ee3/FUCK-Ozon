<script setup lang="ts">
import { NInputNumber } from "naive-ui";

defineProps<{
  title: string;
  currency: string;
  preview: string;
}>();

const amount = defineModel<number | null>("amount", { required: true });
const at = defineModel<string>("at", { required: true });
</script>

<template>
  <fieldset class="complaints-compensation">
    <legend>{{ title }}</legend>
    <label class="complaints-field">平台赔偿金额（{{ currency }}）<NInputNumber v-model:value="amount" :min="0.01" :precision="2" placeholder="0.00" /></label>
    <label class="complaints-field">平台赔偿北京时间<input v-model="at" class="complaints-native-input" type="datetime-local" /></label>
    <div class="complaints-compensation-result">{{ preview }}</div>
  </fieldset>
</template>
