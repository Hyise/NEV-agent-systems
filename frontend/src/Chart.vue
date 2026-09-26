<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from "vue";
import { init, use } from "echarts/core";
import type { EChartsCoreOption, ECharts } from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  AriaComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

use([
  BarChart,
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  AriaComponent,
  CanvasRenderer,
]);
const props = defineProps<{
  option: EChartsCoreOption;
  label: string;
  height?: string;
}>();
const element = ref<HTMLElement>();
let chart: ECharts | undefined;
let observer: ResizeObserver | undefined;
function draw() {
  chart?.setOption(
    {
      animation: false,
      aria: { enabled: true, label: { description: props.label } },
      textStyle: { fontFamily: "Segoe UI, Microsoft YaHei, sans-serif" },
      ...props.option,
    },
    true,
  );
}
onMounted(() => {
  chart = init(element.value!);
  draw();
  observer = new ResizeObserver(() => chart?.resize());
  observer.observe(element.value!);
});
watch(() => props.option, draw, { deep: true });
onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.dispose();
});
</script>

<template>
  <div
    ref="element"
    class="chart"
    role="img"
    :aria-label="label"
    :style="{ height: height || '340px' }"
  />
</template>
