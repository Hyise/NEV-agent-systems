<script setup lang="ts">
import { ArrowLeft, FileClock } from "lucide-vue-next";
import { RouterLink } from "vue-router";
import AppBrand from "../components/AppBrand.vue";

const readiness = [
  {
    title: "研究材料待接入",
    description: "等待原始研究代码、数据结构和方法说明进入审核。",
  },
  {
    title: "业务口径待确认",
    description: "确认评估对象、输入、输出及其可解释边界。",
  },
  {
    title: "后续功能建设",
    description: "在独立的数据与 API 边界内建设评估流程。",
  },
];
</script>

<template>
  <div class="adaptive-introduction">
    <header class="platform-header platform-header--compact">
      <RouterLink to="/" aria-label="返回观衡研究平台">
        <AppBrand compact />
      </RouterLink>
      <span class="adaptive-status">规划中</span>
    </header>

    <main class="adaptive-main">
      <RouterLink class="adaptive-back" to="/">
        <ArrowLeft :size="15" />返回研究平台
      </RouterLink>
      <div class="adaptive-layout">
        <section class="adaptive-intro-copy">
          <p class="platform-kicker">第二研究系统</p>
          <h1>自适应评估系统</h1>
          <p class="adaptive-lead">
            该系统来源于另一项自适应评估研究。研究代码、业务对象和输入输出口径尚未接入本平台。
          </p>
          <div class="adaptive-boundary">
            <FileClock :size="19" />
            <p>
              在研究材料完成审核前，本页不展示模拟指标、示例结果或不可用的业务控件。
            </p>
          </div>
        </section>

        <section class="adaptive-readiness" aria-labelledby="readiness-title">
          <header>
            <span>接入清单</span>
            <h2 id="readiness-title">当前建设状态</h2>
          </header>
          <ol>
            <li v-for="(item, index) in readiness" :key="item.title">
              <span class="mono">{{ String(index + 1).padStart(2, "0") }}</span>
              <div>
                <strong>{{ item.title }}</strong>
                <p>{{ item.description }}</p>
              </div>
            </li>
          </ol>
        </section>
      </div>
    </main>
  </div>
</template>
