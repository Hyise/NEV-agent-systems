<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import { Menu, Plus, X } from "lucide-vue-next";
import { RouterLink } from "vue-router";
import AppBrand from "../../components/AppBrand.vue";
import {
  createCollectionWorkspace,
  provideCollectionWorkspace,
  type CollectionPage,
} from "./workspace";

import OverviewView from "./views/OverviewView.vue";
import JobsView from "./views/JobsView.vue";
import ReviewsView from "./views/ReviewsView.vue";
import SeriesView from "./views/SeriesView.vue";

const pages = [
  {
    id: "overview" as CollectionPage,
    title: "总览",
    subtitle: "查看采集规模与当前运行状态。",
  },
  {
    id: "jobs" as CollectionPage,
    title: "采集任务",
    subtitle: "创建任务，并控制暂停、继续与停止。",
  },
  {
    id: "series" as CollectionPage,
    title: "车系",
    subtitle: "按车系名称或 series_id 查找已发现数据。",
  },
  {
    id: "reviews" as CollectionPage,
    title: "原始评论",
    subtitle: "查看和导出未经拆分、改写的完整口碑对象。",
  },
];

const workspace = createCollectionWorkspace();
provideCollectionWorkspace(workspace);
const {
  page,
  busy,
  actionBusy,
  error,
  mobileNav,
  showCreate,
  jobMode,
  productionConfirmPending,
  productionConfirmationText,
  navigate,
  loadWorkspace,
  openCreate,
  closeCreate,
  createJob,
  confirmProduction,
} = workspace;
const activePage = computed(
  () => pages.find((item) => item.id === page.value)!,
);
const mobileMenuButton = ref<HTMLButtonElement>();
const createDialog = ref<HTMLDialogElement>();
const restoreFocus = ref<HTMLElement | null>(null);

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

function openCreateDialog() {
  restoreFocus.value = document.activeElement as HTMLElement;
  openCreate();
}

function closeCreateDialog() {
  createDialog.value?.close();
  closeCreate();
  restoreFocus.value?.focus();
}

watch(showCreate, async (open) => {
  if (!open) return;
  await nextTick();
  createDialog.value?.showModal();
});

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
      v-if="mobileNav"
      class="nav-backdrop"
      aria-label="关闭导航"
      @click="closeMobileNavigation"
    />
    <aside
      id="collection-navigation"
      class="app-sidebar"
      :class="{ open: mobileNav }"
    >
      <RouterLink class="module-return" to="/" @click="closeMobileNavigation">
        <span aria-hidden="true">←</span>返回研究平台
      </RouterLink>
      <button
        class="brand-link"
        type="button"
        aria-label="返回采集总览"
        @click="navigateTo('overview')"
      >
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
      <div class="sidebar-foot">
        汽车之家数据源 <span class="mono">LOCAL</span>
      </div>
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

      <main
        id="main-content"
        class="collection-main"
        tabindex="-1"
        :aria-busy="busy"
      >
        <div class="heading-row">
          <div>
            <h1>{{ activePage.title }}</h1>
            <p class="subtitle">{{ activePage.subtitle }}</p>
          </div>
          <button
            v-if="page === 'overview' || page === 'jobs'"
            class="btn primary"
            :disabled="
              busy ||
              actionBusy ||
              Boolean(workspace.overview.value?.active_job)
            "
            @click="openCreateDialog"
          >
            <Plus :size="17" />新建任务
          </button>
        </div>
        <div v-if="error" class="notice error" role="alert">
          <span>{{ error }}</span>
          <button class="text-button" @click="loadWorkspace">重新加载</button>
        </div>
        <div v-if="busy" class="loading-line" role="status" aria-live="polite">
          正在读取采集数据…
        </div>
        <OverviewView v-if="!busy && page === 'overview'" />
        <JobsView v-else-if="!busy && page === 'jobs'" />
        <SeriesView v-else-if="!busy && page === 'series'" />
        <ReviewsView v-else-if="!busy && page === 'reviews'" />
      </main>
    </div>

    <dialog
      v-if="showCreate"
      ref="createDialog"
      class="project-dialog collection-job-dialog"
      aria-labelledby="create-collection-job-title"
      @cancel.prevent="closeCreateDialog"
    >
      <form
        @submit.prevent="
          productionConfirmPending ? confirmProduction() : createJob()
        "
      >
        <div class="dialog-heading">
          <div>
            <p class="collection-eyebrow">汽车之家口碑</p>
            <h2 id="create-collection-job-title">新建采集任务</h2>
          </div>
          <button
            class="icon-btn"
            type="button"
            aria-label="关闭新建任务"
            :disabled="actionBusy"
            @click="closeCreateDialog"
          >
            <X :size="20" />
          </button>
        </div>
        <fieldset class="mode-options">
          <legend>运行范围</legend>
          <label
            :class="['mode-option', { selected: jobMode === 'verification' }]"
          >
            <input
              v-model="jobMode"
              name="collection-mode"
              type="radio"
              value="verification"
              :disabled="actionBusy"
              @change="productionConfirmPending = false"
            />
            <span
              ><strong>功能验证</strong
              ><small
                >最多 3 个车系，每个车系 2 页。适合首次运行与功能检查。</small
              ></span
            >
          </label>
          <label
            :class="['mode-option', { selected: jobMode === 'production' }]"
          >
            <input
              v-model="jobMode"
              name="collection-mode"
              type="radio"
              value="production"
              :disabled="actionBusy"
              @change="productionConfirmPending = false"
            />
            <span
              ><strong>正式采集</strong
              ><small>前 500 个唯一车系，每个车系采集全部评论。</small></span
            >
          </label>
        </fieldset>
        <p v-if="productionConfirmPending" class="notice info" role="status">
          {{ productionConfirmationText }}
        </p>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <button
          class="btn primary full-width"
          type="submit"
          :disabled="actionBusy"
        >
          {{
            actionBusy
              ? "正在创建…"
              : productionConfirmPending
                ? "确认并开始正式采集"
                : "创建任务"
          }}
        </button>
      </form>
    </dialog>
  </div>
</template>
