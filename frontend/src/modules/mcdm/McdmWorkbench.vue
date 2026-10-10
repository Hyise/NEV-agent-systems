<script setup lang="ts">
import {
  computed,
  defineAsyncComponent,
  onBeforeUnmount,
  onMounted,
  ref,
} from "vue";
import { ArrowRight, Check, Menu, Plus, X } from "lucide-vue-next";
import { RouterLink } from "vue-router";
import AppBrand from "../../components/AppBrand.vue";
import { createReviewAnalysisApi } from "./review-analysis/api";
import {
  createReviewAnalysisWorkspace,
  provideReviewAnalysisWorkspace,
} from "./review-analysis/workspace";
import { createWorkspace, provideWorkspace, type Page } from "./workspace";

const OverviewView = defineAsyncComponent(
  () => import("./views/OverviewView.vue"),
);
const DataView = defineAsyncComponent(() => import("./views/DataView.vue"));
const CriteriaView = defineAsyncComponent(
  () => import("./views/CriteriaView.vue"),
);
const ReviewAnalysisView = defineAsyncComponent(
  () => import("./views/ReviewAnalysisView.vue"),
);
const ScenarioView = defineAsyncComponent(
  () => import("./views/ScenarioView.vue"),
);
const SharesView = defineAsyncComponent(() => import("./views/SharesView.vue"));
const ExperimentsView = defineAsyncComponent(
  () => import("./views/ExperimentsView.vue"),
);

const pages = [
  {
    id: "overview" as Page,
    title: "研究总览",
    subtitle: "从用户评价，理解市场选择。",
  },
  {
    id: "data" as Page,
    title: "数据中心",
    subtitle: "追溯每一次分析的数据起点。",
  },
  {
    id: "criteria" as Page,
    title: "准则工作台",
    subtitle: "让评价维度有定义，让研究版本可追溯。",
  },
  {
    id: "review-analysis" as Page,
    title: "评论语义分析",
    subtitle: "从完整评论发现准则，并按冻结体系逐条提取评价证据。",
  },
  {
    id: "scenario" as Page,
    title: "情景分析",
    subtitle: "观察时间压力下的权重变化。",
  },
  {
    id: "shares" as Page,
    title: "份额分析",
    subtitle: "在同一候选集内，对照真实份额与模型估计。",
  },
  {
    id: "experiments" as Page,
    title: "实验档案",
    subtitle: "保留研究证据，也保留它的适用边界。",
  },
];

const pageGroups = [
  { label: "研究准备", pages: pages.slice(0, 4) },
  { label: "分析复核", pages: pages.slice(4) },
];

const workspace = createWorkspace();
provideWorkspace(workspace);
const {
  page,
  projects,
  projectId,
  overview,
  month,
  busy,
  saving,
  error,
  message,
  mobileNav,
  showCreate,
  projectName,
  createMode,
  createDialog,
  projectNameInput,
  isPreset,
  editable,
  isDirty,
  navigate,
  openCreate,
  closeCreate,
  createProject,
  changeProject,
  changeMonth,
  loadWorkspace,
} = workspace;
const reviewAnalysisWorkspace = createReviewAnalysisWorkspace(
  createReviewAnalysisApi(),
  projectId,
  workspace.schemaId,
  computed(() => overview.value?.schema.status ?? "draft"),
);
provideReviewAnalysisWorkspace(reviewAnalysisWorkspace);
const activePage = computed(
  () => pages.find((item) => item.id === page.value)!,
);
const currentProjectName = computed(
  () =>
    projects.value.find((project) => project.id === projectId.value)?.name ??
    "未选择分析项目",
);
const mobileMenuButton = ref<HTMLButtonElement>();

function closeMobileNavigation() {
  const shouldRestoreFocus = mobileNav.value;
  mobileNav.value = false;
  if (shouldRestoreFocus) {
    requestAnimationFrame(() => mobileMenuButton.value?.focus());
  }
}

function navigateTo(value: Page) {
  const shouldRestoreFocus = mobileNav.value;
  navigate(value);
  if (shouldRestoreFocus) {
    requestAnimationFrame(() => mobileMenuButton.value?.focus());
  }
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
  <div class="mcdm-shell">
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
      id="primary-navigation"
      class="app-sidebar"
      :class="{ open: mobileNav }"
    >
      <RouterLink class="module-return" to="/" @click="closeMobileNavigation">
        <span aria-hidden="true">←</span>返回研究平台
      </RouterLink>
      <button
        class="brand-link"
        type="button"
        aria-label="返回多准则研究总览"
        @click="navigateTo('overview')"
      >
        <AppBrand compact />
      </button>
      <p class="workspace-label">多准则决策系统</p>
      <nav aria-label="主导航">
        <section
          v-for="group in pageGroups"
          :key="group.label"
          class="nav-group"
        >
          <h2 class="nav-group__title">{{ group.label }}</h2>
          <button
            v-for="item in group.pages"
            :key="item.id"
            :class="['nav-item', { active: page === item.id }]"
            :aria-current="page === item.id ? 'page' : undefined"
            @click="navigateTo(item.id)"
          >
            <span>{{ item.title }}</span>
          </button>
        </section>
      </nav>
      <div class="sidebar-foot">本机研究版 <span class="mono">0.1</span></div>
    </aside>

    <div class="mcdm-workspace">
      <header class="mcdm-platform-bar">
        <button
          ref="mobileMenuButton"
          class="icon-btn mobile-menu"
          aria-label="打开导航"
          aria-controls="primary-navigation"
          :aria-expanded="mobileNav"
          @click="mobileNav = !mobileNav"
        >
          <Menu :size="22" />
        </button>
        <div class="platform-bar__identity">
          <span class="platform-bar__module">多准则决策系统</span>
          <span aria-hidden="true">/</span>
          <strong>{{ activePage.title }}</strong>
        </div>
        <RouterLink class="platform-return" to="/">返回研究平台</RouterLink>
      </header>

      <main id="main-content" class="mcdm-main" tabindex="-1" :aria-busy="busy">
        <div class="heading-row">
          <div>
            <h1>{{ activePage.title }}</h1>
            <p class="subtitle">{{ activePage.subtitle }}</p>
          </div>
          <button
            class="btn primary"
            :disabled="saving || busy || (editable && isDirty)"
            @click="openCreate()"
          >
            <Plus :size="17" />新建研究
          </button>
        </div>

        <section class="research-context" aria-label="当前研究上下文">
          <span class="research-context__label">研究上下文</span>
          <label class="project-control">
            <span>分析项目</span>
            <select
              v-model="projectId"
              aria-label="分析项目"
              name="analysis-project"
              :title="currentProjectName"
              :disabled="busy || saving || (editable && isDirty)"
              @change="changeProject"
            >
              <option
                v-for="project in projects"
                :key="project.id"
                :value="project.id"
              >
                {{ project.name }}
              </option>
            </select>
          </label>
          <span v-if="overview" class="context-mode">
            {{ isPreset ? "预置准则模式" : "自定义准则模式" }}
          </span>
          <label
            v-if="
              overview &&
              !['criteria', 'experiments', 'review-analysis'].includes(page)
            "
            class="month-control"
          >
            <span>观察月份</span>
            <select
              v-model="month"
              name="observation-month"
              :disabled="busy || !overview.months.length"
              @change="changeMonth"
            >
              <option v-if="!overview.months.length" value="">暂无数据</option>
              <option v-for="item in overview.months" :key="item">
                {{ item }}
              </option>
            </select>
          </label>
          <span v-if="overview" class="context-version mono"
            >准则 V{{ overview.schema.version }}</span
          >
        </section>

        <div v-if="error" class="notice error" role="alert">
          <span>{{ error }}</span
          ><button class="text-button" @click="loadWorkspace">重新加载</button>
        </div>
        <div v-if="busy" class="loading-line" role="status" aria-live="polite">
          正在读取研究数据…
        </div>

        <template v-if="overview">
          <OverviewView v-if="page === 'overview'" />
          <DataView v-else-if="page === 'data'" />
          <CriteriaView v-else-if="page === 'criteria'" />
          <ReviewAnalysisView v-else-if="page === 'review-analysis'" />
          <ScenarioView v-else-if="page === 'scenario'" />
          <SharesView v-else-if="page === 'shares'" />
          <ExperimentsView v-else-if="page === 'experiments'" />
          <footer class="main-footer">
            <span>观衡 · 新能源汽车情景多准则决策分析系统</span>
            <span>{{
              isPreset
                ? "来源：llm-beast-mcdm 研究归档"
                : "自定义研究 · 本机持久化"
            }}</span>
          </footer>
        </template>
        <div v-else-if="!busy && !error" class="empty">
          <p>正在初始化研究空间。</p>
        </div>
      </main>
    </div>

    <div v-if="message" class="toast" role="status">
      <Check :size="17" />{{ message }}
    </div>
    <dialog
      v-if="showCreate"
      ref="createDialog"
      class="project-dialog"
      aria-labelledby="create-project-title"
      @cancel.prevent="closeCreate"
    >
      <form @submit.prevent="createProject">
        <div class="dialog-heading">
          <h2 id="create-project-title">建立分析项目</h2>
          <button
            class="icon-btn"
            type="button"
            aria-label="关闭新建项目"
            :disabled="saving"
            @click="closeCreate"
          >
            <X :size="20" />
          </button>
        </div>
        <label class="form-label">
          项目名称
          <input
            ref="projectNameInput"
            v-model="projectName"
            name="project-name"
            autocomplete="off"
            required
            maxlength="100"
            placeholder="例如：纯电轿车用户评价研究…"
            :disabled="saving"
          />
        </label>
        <fieldset class="mode-options">
          <legend>选择工作模式</legend>
          <label
            :class="['mode-option', { selected: createMode === 'preset' }]"
          >
            <input
              v-model="createMode"
              name="project-mode"
              type="radio"
              value="preset"
              :disabled="saving"
            />
            <span
              ><strong>预置研究分析</strong
              ><small>10项准则与真实归档数据，快速浏览研究结果。</small></span
            >
          </label>
          <label
            :class="['mode-option', { selected: createMode === 'custom' }]"
          >
            <input
              v-model="createMode"
              name="project-mode"
              type="radio"
              value="custom"
              :disabled="saving"
            />
            <span
              ><strong>自定义准则研究</strong
              ><small
                >从预置准则草稿起步，编辑等级、冻结版本并导入自己的数据。</small
              ></span
            >
          </label>
        </fieldset>
        <p class="caption">
          此阶段提供数据与准则工作流；在线评论分析和新模型训练将在后续接入。
        </p>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <button
          class="btn primary full-width"
          type="submit"
          :disabled="saving || !projectName.trim()"
        >
          {{ saving ? "正在创建…" : "创建项目" }}<ArrowRight :size="16" />
        </button>
      </form>
    </dialog>
  </div>
</template>
