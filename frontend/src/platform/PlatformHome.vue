<script setup lang="ts">
import { ArrowRight } from "lucide-vue-next";
import { RouterLink } from "vue-router";
import AppBrand from "../components/AppBrand.vue";
import { researchModules, type ModuleId } from "./modules";

interface ModulePresentation {
  role: string;
  summary: string;
  capabilities: readonly string[];
  footnote: string;
}

const presentations: Record<ModuleId, ModulePresentation> = {
  collection: {
    role: "数据基础",
    summary: "发现汽车之家车系，采集并保存完整原始口碑。",
    capabilities: [
      "发现新能源汽车车系",
      "保存完整原始评论",
      "查询、追溯与研究交接",
    ],
    footnote: "支持限速、暂停和断点续采",
  },
  mcdm: {
    role: "研究核心",
    summary: "从完整评论建立评价准则与证据，再结合销量复核市场选择。",
    capabilities: [
      "大模型准则发现与评论标注",
      "准则—权重—情景模型",
      "份额比较与实验复核",
    ],
    footnote: "数据、版本、来源与研究局限均可追溯",
  },
  adaptive: {
    role: "后续研究",
    summary: "第二项研究将在材料和业务口径确认后独立接入。",
    capabilities: ["研究材料待接入", "业务口径待确认", "后续功能建设"],
    footnote: "当前不提供评估功能或演示数据",
  },
};

const primaryModules = researchModules.filter(
  (module) => module.status === "available",
);
const adaptiveModule = researchModules.find(
  (module) => module.id === "adaptive",
)!;
const evidenceSteps = ["发现车系", "原始评论", "准则证据", "决策复核"];

function focusDirectory() {
  document.querySelector<HTMLElement>("#platform-directory")?.focus();
}
</script>

<template>
  <div class="platform-home">
    <a
      class="skip-link"
      href="#platform-directory"
      @click.prevent="focusDirectory"
      >跳转到系统目录</a
    >
    <header class="platform-header">
      <AppBrand />
      <div class="platform-header__meta">
        <span>新能源汽车评价研究</span>
        <span>本机研究版 0.1</span>
      </div>
    </header>

    <main id="platform-directory" class="platform-main" tabindex="-1">
      <section class="platform-intro" aria-labelledby="platform-title">
        <p class="platform-kicker">新能源用户评价与决策研究</p>
        <h1 id="platform-title">观衡研究平台</h1>
        <p>
          从公开评论建立可追溯的评价证据，再将用户感知与市场选择放在同一研究框架中复核。
        </p>
      </section>

      <nav class="platform-evidence-chain" aria-label="研究证据链">
        <span>研究证据链</span>
        <ol>
          <li v-for="(step, index) in evidenceSteps" :key="step">
            <span class="mono">{{ String(index + 1).padStart(2, "0") }}</span>
            <strong>{{ step }}</strong>
          </li>
        </ol>
      </nav>

      <section class="module-directory" aria-label="已开放研究系统">
        <article
          v-for="module in primaryModules"
          :key="module.id"
          :class="[
            'module-entry',
            {
              'module-entry--collection': module.id === 'collection',
              'module-entry--mcdm': module.id === 'mcdm',
            },
          ]"
          :style="{ '--module-accent': module.accent }"
        >
          <header class="module-entry__header">
            <span class="module-entry__role">{{
              presentations[module.id].role
            }}</span>
            <span class="module-entry__status">{{ module.statusLabel }}</span>
          </header>
          <div class="module-entry__body">
            <h2>{{ module.name }}</h2>
            <p>{{ presentations[module.id].summary }}</p>
            <ul class="module-capabilities">
              <li
                v-for="capability in presentations[module.id].capabilities"
                :key="capability"
              >
                {{ capability }}
              </li>
            </ul>
          </div>
          <footer class="module-entry__footer">
            <span>{{ presentations[module.id].footnote }}</span>
            <RouterLink :to="module.path">
              {{ module.actionLabel }}<ArrowRight :size="16" />
            </RouterLink>
          </footer>
        </article>
      </section>

      <RouterLink
        class="adaptive-entry"
        :to="adaptiveModule.path"
        :style="{ '--module-accent': adaptiveModule.accent }"
      >
        <span class="adaptive-entry__role">03 · 后续研究</span>
        <span class="adaptive-entry__copy">
          <strong>{{ adaptiveModule.name }}</strong>
          <small>{{ presentations.adaptive.summary }}</small>
        </span>
        <span class="adaptive-entry__status">{{
          adaptiveModule.statusLabel
        }}</span>
        <ArrowRight :size="17" aria-hidden="true" />
      </RouterLink>
    </main>

    <footer class="platform-footer">
      <span>观衡 · 新能源汽车研究平台</span>
      <span>研究数据仅保存在本机</span>
    </footer>
  </div>
</template>
