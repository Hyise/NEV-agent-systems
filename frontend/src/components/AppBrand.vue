<script setup lang="ts">
withDefaults(defineProps<{ compact?: boolean }>(), {
  compact: false,
});
</script>

<template>
  <span :class="['app-brand', { 'app-brand--compact': compact }]">
    <span class="app-brand__mark" aria-hidden="true">
      <svg viewBox="0 0 44 44" role="presentation">
        <path class="app-brand__axis" d="M8 7v29h29" />
        <path class="app-brand__review" d="m12 29 7-9 7 4 8-13" />
        <circle class="app-brand__market" cx="34" cy="11" r="3" />
      </svg>
    </span>
    <span class="app-brand__copy">
      <strong>观衡</strong>
      <small>NEV DECISION RESEARCH</small>
    </span>
  </span>
</template>
