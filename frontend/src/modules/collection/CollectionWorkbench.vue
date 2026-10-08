<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { Menu } from "lucide-vue-next";
import { RouterLink } from "vue-router";
import AppBrand from "../../components/AppBrand.vue";
import {
  createCollectionWorkspace,
  provideCollectionWorkspace,
  type CollectionPage,
} from "./workspace";

const pages = [
  { id: "overview" as CollectionPage, title: "总览", subtitle: "查看采集规模与当前运行状态。" },
  { id: "jobs" as CollectionPage, title: "采集任务", subtitle: "创建任务，并控制暂停、继续与停止。" },
  { id: "series" as CollectionPage, title: "车系", subtitle: "按车系名称或 series_id 查找已发现数据。" },
  { id: "reviews" as CollectionPage, title: "原始评论", subtitle: "查看和导出未经拆分、改写的完整口碑对象。" },
];

const workspace = createCollectionWorkspace();
provideCollectionWorkspace(workspace);
const { page, busy, error, mobileNav, navigate, loadWorkspace } = workspace;
const activePage = computed(() => pages.find((item) => item.id === page.value)!);
const mobileMenuButton = ref<HTMLButtonElement>();

function closeMobileNavigation() {
  const restore = mobileNav.value;
  mobileNav.value = false;
  if (restore) requestAnimationFrame(() => mobileMenuButton.value?.focus());
}

function navigateTo(value: CollectionPage) {
  const restore = mobileNav.value;
  navigate(value);
  if (restore) requestAnimationFrame(() => mobileMenuButton.value?.focus());
}

function focusMain() {
  document.querySelector<HTMLElement>("#main-content")?.focus();
}

function escapeNavigation(event: KeyboardEvent) {
  if (event.key === "Escape") closeMobileNavigation();
}

onMounted(() => document.addEventListener("keydown", escapeNavigation));
onBeforeUnmount(() => document.removeEventListener("keydown", escapeNavigation));
</script>

<template>
  <div class="collection-shell">
    <a class="skip-link" href="#main-content" @click.prevent="focusMain">跳转到主内容</a>
    <button
      v-if="mobileNav"
      class="nav-backdrop"
      aria-label="关闭导航"
      @click="closeMobileNavigation"
    />
    <aside id="collection-navigation" class="app-sidebar" :class="{ open: mobileNav }">
      <RouterLink class="module-return" to="/" @click="closeMobileNavigation">
        <span aria-hidden="true">←</span>返回研究平台
      </RouterLink>
      <button class="brand-link" type="button" aria-label="返回采集总览" @click="navigateTo('overview')">
        <AppBrand compact />
      </button>
      <p class="workspace-label">评论数据采集系统</p>
      <nav aria-label="采集系统导航">
        <button
          v-for="item in pages"
          :key="item.id"
          :class="['nav-item', { active: page === item.id }]"
          :aria-current="page === item.id ? 'page' : undefined"
          @click="navigateTo(item.id)"
        >
          <span>{{ item.title }}</span>
        </button>
      </nav>
      <div class="sidebar-foot">汽车之家数据源 <span class="mono">LOCAL</span></div>
    </aside>

    <div class="collection-workspace">
      <header class="collection-platform-bar">
        <button
          ref="mobileMenuButton"
          class="icon-btn mobile-menu"
          aria-label="打开导航"
          aria-controls="collection-navigation"
          :aria-expanded="mobileNav"
          @click="mobileNav = !mobileNav"
        >
          <Menu :size="22" />
        </button>
        <div class="platform-bar__identity">
          <span class="platform-bar__module">评论数据采集系统</span>
          <span aria-hidden="true">/</span>
          <strong>{{ activePage.title }}</strong>
        </div>
        <RouterLink class="platform-return" to="/">返回研究平台</RouterLink>
      </header>

      <main id="main-content" class="collection-main" tabindex="-1" :aria-busy="busy">
        <div class="heading-row">
          <div>
            <h1>{{ activePage.title }}</h1>
            <p class="subtitle">{{ activePage.subtitle }}</p>
          </div>
        </div>
        <div v-if="error" class="notice error" role="alert">
          <span>{{ error }}</span>
          <button class="text-button" @click="loadWorkspace">重新加载</button>
        </div>
        <div v-if="busy" class="loading-line" role="status" aria-live="polite">正在读取采集数据…</div>
        <section v-else class="collection-placeholder" aria-live="polite">
          <h2>{{ activePage.title }}</h2>
          <p>页面功能将在当前实施阶段继续接入。</p>
        </section>
      </main>
    </div>
  </div>
</template>
