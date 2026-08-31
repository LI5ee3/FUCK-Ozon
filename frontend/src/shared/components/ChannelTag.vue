<script setup lang="ts">
import type { Channel } from "../types/common";

defineProps<{ channel: Channel }>();
const tones: Record<Channel, string> = { FBP: "azure", realFBS: "mint", WHD: "butter" };
</script>

<template>
  <span class="opanel-channel-tag" :class="`tone-${tones[channel]}`"><slot>{{ channel }}</slot></span>
</template>
