<script setup lang="ts">
import { RouterLink } from "vue-router";
import AppBrand from "../components/AppBrand.vue";

const readiness = ["研究材料待接入", "业务口径待确认", "后续功能建设"];
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
      <p class="platform-kicker">第二研究系统</p>
      <h1>自适应评估系统</h1>
      <p class="adaptive-lead">
        该系统来源于另一项自适应评估研究。研究代码、业务对象和输入输出口径尚未接入本平台。
      </p>

      <section class="adaptive-readiness" aria-labelledby="readiness-title">
        <h2 id="readiness-title">当前建设状态</h2>
        <ol>
          <li v-for="(item, index) in readiness" :key="item">
            <span>{{ String(index + 1).padStart(2, "0") }}</span>
            <strong>{{ item }}</strong>
          </li>
        </ol>
      </section>

      <p class="adaptive-boundary">
        在研究材料完成审核前，本页不展示模拟指标、示例结果或不可用的业务控件。
      </p>
      <RouterLink class="platform-action" to="/">返回研究平台</RouterLink>
    </main>
  </div>
</template>
