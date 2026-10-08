<script setup lang="ts">
import { RouterLink } from "vue-router";
import AppBrand from "../components/AppBrand.vue";
import { researchModules, type ModuleId } from "./modules";

interface ModulePresentation {
  summary: string;
  pathLabel: string;
  steps: readonly string[];
  footnote: string;
}

const presentations: Record<ModuleId, ModulePresentation> = {
  collection: {
    summary: "发现汽车之家车系，采集并保存完整原始口碑。",
    pathLabel: "数据采集范围",
    steps: ["新能源汽车车系", "完整原始口碑", "查询与 JSONL 导出"],
    footnote: "支持限速、暂停、断点续采和原始数据追溯",
  },
  mcdm: {
    summary: "以用户评论构建评价准则，并结合销量观察市场选择。",
    pathLabel: "研究证据路径",
    steps: ["用户评论与销量", "准则—权重—情景模型", "份额比较与实验复核"],
    footnote: "数据、准则版本与研究局限均可追溯",
  },
  adaptive: {
    summary: "第二项研究将在材料和业务口径确认后独立接入。",
    pathLabel: "系统建设路径",
    steps: ["研究材料待接入", "业务口径待确认", "后续功能建设"],
    footnote: "当前不提供评估功能或演示数据",
  },
};

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
      <div class="platform-intro">
        <p class="platform-kicker">研究系统目录</p>
        <h1>观衡研究平台</h1>
        <p>
          选择要进入的功能系统。三个子系统共享工程基础，但数据、状态和研究方法相互独立。
        </p>
      </div>

      <section class="module-directory" aria-label="研究系统">
        <article
          v-for="(module, index) in researchModules"
          :key="module.id"
          :class="['module-entry', 'module-entry--' + module.status]"
          :style="{ '--module-accent': module.accent }"
        >
          <header class="module-entry__header">
            <span class="module-entry__index" aria-hidden="true">{{
              String(index + 1).padStart(2, "0")
            }}</span>
            <span class="module-entry__status">{{ module.statusLabel }}</span>
          </header>

          <div class="module-entry__body">
            <h2>{{ module.name }}</h2>
            <p>{{ presentations[module.id].summary }}</p>

            <div class="research-path">
              <span class="research-path__label">{{
                presentations[module.id].pathLabel
              }}</span>
              <ol>
                <li v-for="step in presentations[module.id].steps" :key="step">
                  <span>{{ step }}</span>
                </li>
              </ol>
            </div>
          </div>

          <footer class="module-entry__footer">
            <span>{{ presentations[module.id].footnote }}</span>
            <RouterLink :to="module.path">{{ module.actionLabel }}</RouterLink>
          </footer>
        </article>
      </section>
    </main>

    <footer class="platform-footer">
      <span>观衡 · 新能源汽车研究平台</span>
      <span>研究数据仅保存在本机</span>
    </footer>
  </div>
</template>
