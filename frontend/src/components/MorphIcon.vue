<script setup lang="ts">
import { MorphIcon as OfficialMorphIcon } from "morphicons/vue";
import { getIcon, type IconName } from "../icons/tabler";

withDefaults(
  defineProps<{
    icon: IconName;
    size?: number | string;
    strokeWidth?: number | string;
  }>(),
  { size: 20, strokeWidth: 1.5 },
);
</script>

<template>
  <OfficialMorphIcon
    class="morph-icon"
    :icon="getIcon(icon)"
    :size="size"
    :stroke-width="strokeWidth"
  />
</template>
