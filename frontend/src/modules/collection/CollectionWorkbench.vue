<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { Component } from "vue";
import { Download, FlaskConical, Library, Menu } from "lucide-vue-next";
import { RouterLink } from "vue-router";
import AppBrand from "../../components/AppBrand.vue";
import type { AcquisitionAction } from "./acquisitionGuidance";
import { createAssetWorkspace } from "./assetWorkspace";
import { createCatalogFlow } from "./catalogFlow";
import CreateCollectionJobDialog from "./components/CreateCollectionJobDialog.vue";
import GuidedStageBar from "./components/GuidedStageBar.vue";
import {
  createCollectionWorkspace,
  provideCollectionWorkspace,
  type CollectionPage,
} from "./workspace";
import AcquireView from "./views/AcquireView.vue";
import AssetsView from "./views/AssetsView.vue";
import ResearchHandoffView from "./views/ResearchHandoffView.vue";

const pages: Array<{
  id: CollectionPage;
  title: string;
  subtitle: string;
  icon: Component;
}> = [
  {
    id: "acquire",
    title: "获取数据",
    subtitle: "发现车系、选择范围并运行评论采集任务。",
    icon: Download,
  },
  {
    id: "assets",
    title: "管理数据",
    subtitle: "检查原始评论，维护研究标签和分析状态。",
    icon: Library,
  },
  {
    id: "research",
    title: "用于研究",
    subtitle: "确认可用规模，再进入多准则研究流程。",
    icon: FlaskConical,
  },
];

const workspace = createCollectionWorkspace();
provideCollectionWorkspace(workspace);
const assetWorkspace = createAssetWorkspace();
const catalogFlow = createCatalogFlow(undefined, workspace.loadWorkspace);
const activePage = computed(
  () => pages.find((item) => item.id === workspace.page.value)!,
);
const mobileMenuButton = ref<HTMLButtonElement>();

function closeMobileNavigation() {
  const restore = workspace.mobileNav.value;
  workspace.mobileNav.value = false;
  if (restore) requestAnimationFrame(() => mobileMenuButton.value?.focus());
}

function navigateTo(page: CollectionPage) {
  const restore = workspace.mobileNav.value;
  workspace.navigate(page);
  if (page === "assets" || page === "research") void assetWorkspace.refresh();
  if (restore) requestAnimationFrame(() => mobileMenuButton.value?.focus());
}

watch(
  () => workspace.overview.value?.review_count,
  (next, previous) => {
    if (previous !== undefined && next !== previous)
      void assetWorkspace.refresh();
  },
);

function runGuidedAction(action: AcquisitionAction) {
  const activeJob = workspace.overview.value?.active_job;
  if (action === "manage") navigateTo("assets");
  else if (action === "resume" && activeJob)
    void workspace.resume(activeJob.id);
  else if (action === "monitor")
    document.querySelector<HTMLElement>("#current-collection-job")?.focus();
  else void catalogFlow.open();
}

function focusMain() {
  document.querySelector<HTMLElement>("#main-content")?.focus();
}

function escapeNavigation(event: KeyboardEvent) {
  if (event.key === "Escape") closeMobileNavigation();
}

onMounted(() => document.addEventListener("keydown", escapeNavigation));
onBeforeUnmount(() =>
  document.removeEventListener("keydown", escapeNavigation),
);
</script>

<template>
  <div class="collection-shell">
    <a class="skip-link" href="#main-content" @click.prevent="focusMain"
      >跳转到主内容</a
    >
    <button
      v-if="workspace.mobileNav.value"
      class="nav-backdrop"
      aria-label="关闭导航"
      @click="closeMobileNavigation"
    />
    <aside
      id="collection-navigation"
      class="app-sidebar"
      :class="{ open: workspace.mobileNav.value }"
    >
      <RouterLink class="module-return" to="/" @click="closeMobileNavigation"
        ><span aria-hidden="true">←</span>返回研究平台</RouterLink
      >
      <button
        class="brand-link"
        type="button"
        aria-label="返回获取数据"
        @click="navigateTo('acquire')"
      >
        <AppBrand compact />
      </button>
      <p class="workspace-label">评论数据工作台</p>
      <nav aria-label="评论数据工作台导航">
        <button
          v-for="item in pages"
          :key="item.id"
          :class="['nav-item', { active: workspace.page.value === item.id }]"
          :aria-current="workspace.page.value === item.id ? 'page' : undefined"
          @click="navigateTo(item.id)"
        >
          <component
            :is="item.icon"
            class="nav-item__icon"
            :size="16"
            aria-hidden="true"
          />
          <span>{{ item.title }}</span>
        </button>
      </nav>
      <div class="sidebar-foot">
        本机研究数据 <span class="mono">LOCAL</span>
      </div>
    </aside>

    <div class="collection-workspace">
      <header class="collection-platform-bar">
        <button
          ref="mobileMenuButton"
          class="icon-btn mobile-menu"
          aria-label="打开导航"
          aria-controls="collection-navigation"
          :aria-expanded="workspace.mobileNav.value"
          @click="workspace.mobileNav.value = !workspace.mobileNav.value"
        >
          <Menu :size="22" />
        </button>
        <div class="platform-bar__identity">
          <span class="platform-bar__module">评论数据工作台</span
          ><span aria-hidden="true">/</span
          ><strong>{{ activePage.title }}</strong>
        </div>
        <RouterLink class="platform-return" to="/">返回研究平台</RouterLink>
      </header>

      <main
        id="main-content"
        class="collection-main"
        tabindex="-1"
        :aria-busy="workspace.busy.value"
      >
        <div class="heading-row">
          <div>
            <h1>{{ activePage.title }}</h1>
            <p class="subtitle">{{ activePage.subtitle }}</p>
          </div>
        </div>
        <GuidedStageBar
          :current="workspace.page.value"
          :overview="workspace.overview.value"
          :catalog="catalogFlow.catalogStatus.value"
          @navigate="navigateTo"
          @action="runGuidedAction"
        />
        <div v-if="workspace.error.value" class="notice error" role="alert">
          <span>{{ workspace.error.value }}</span
          ><button class="text-button" @click="workspace.loadWorkspace">
            重新加载
          </button>
        </div>
        <div
          v-if="workspace.busy.value"
          class="loading-line"
          role="status"
          aria-live="polite"
        >
          正在读取采集数据…
        </div>
        <AcquireView
          v-if="!workspace.busy.value && workspace.page.value === 'acquire'"
          :catalog-flow="catalogFlow"
          @manage="navigateTo('assets')"
        />
        <AssetsView
          v-else-if="workspace.page.value === 'assets'"
          :workspace="assetWorkspace"
        />
        <ResearchHandoffView
          v-else-if="workspace.page.value === 'research'"
          :workspace="assetWorkspace"
        />
      </main>
    </div>

    <CreateCollectionJobDialog
      :flow="catalogFlow"
      :collection-conflict="Boolean(workspace.overview.value?.active_job)"
    />
  </div>
</template>
