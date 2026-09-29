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
const bodyFont = 'SimSun, "宋体", STSong, "Songti SC", serif';
const dataFont = 'SimSun, "宋体", STSong, "Songti SC", serif';

function draw() {
  chart?.setOption(
    {
      ...props.option,
      animation: false,
      color: ["#0f7c82", "#c65a3a", "#6f8e98", "#a6b7bd"],
      aria: { enabled: true, label: { description: props.label } },
      textStyle: { color: "#536673", fontFamily: bodyFont },
      tooltip: {
        borderWidth: 1,
        borderColor: "#d9e0e5",
        backgroundColor: "#ffffff",
        textStyle: { color: "#1e2b38", fontFamily: dataFont, fontSize: 12 },
        ...(props.option.tooltip || {}),
      },
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
