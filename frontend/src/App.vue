<script setup lang="ts">
import {
  computed,
  defineAsyncComponent,
  onBeforeUnmount,
  onMounted,
} from "vue";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Check,
  ChevronRight,
  Database,
  FlaskConical,
  Layers3,
  LayoutDashboard,
  Menu,
  Plus,
  SlidersHorizontal,
  X,
} from "lucide-vue-next";
import { createWorkspace, provideWorkspace, type Page } from "./workspace";

const OverviewView = defineAsyncComponent(
  () => import("./views/OverviewView.vue"),
);
const DataView = defineAsyncComponent(() => import("./views/DataView.vue"));
const CriteriaView = defineAsyncComponent(
  () => import("./views/CriteriaView.vue"),
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
    icon: LayoutDashboard,
    subtitle: "从用户评价，理解市场选择。",
  },
  {
    id: "data" as Page,
    title: "数据中心",
    icon: Database,
    subtitle: "追溯每一次分析的数据起点。",
  },
  {
    id: "criteria" as Page,
    title: "准则工作台",
    icon: Layers3,
    subtitle: "让评价维度有定义，让研究版本可追溯。",
  },
  {
    id: "scenario" as Page,
    title: "情景分析",
    icon: SlidersHorizontal,
    subtitle: "观察时间压力下的权重变化。",
  },
  {
    id: "shares" as Page,
    title: "份额分析",
    icon: BarChart3,
    subtitle: "在同一候选集内，对照真实份额与模型估计。",
  },
  {
    id: "experiments" as Page,
    title: "实验档案",
    icon: FlaskConical,
    subtitle: "保留研究证据，也保留它的适用边界。",
  },
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
const activePage = computed(
  () => pages.find((item) => item.id === page.value)!,
);

function escapeNavigation(event: KeyboardEvent) {
  if (event.key === "Escape") mobileNav.value = false;
}

onMounted(() => document.addEventListener("keydown", escapeNavigation));
onBeforeUnmount(() =>
  document.removeEventListener("keydown", escapeNavigation),
);
</script>

<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">跳转到主内容</a>
    <button
      v-if="mobileNav"
      class="nav-backdrop"
      aria-label="关闭导航"
      @click="mobileNav = false"
    />
    <aside class="sidebar" :class="{ open: mobileNav }">
      <a class="brand" href="#" @click.prevent="navigate('overview')">
        <span class="brand-mark"><BarChart3 :size="24" /></span>
        <span>观衡<span class="brand-en">MCDM RESEARCH</span></span>
      </a>
      <div class="workspace-label">新能源汽车研究工作台</div>
      <nav aria-label="主导航">
        <button
          v-for="item in pages"
          :key="item.id"
          :class="['nav-item', { active: page === item.id }]"
          :aria-current="page === item.id ? 'page' : undefined"
          @click="navigate(item.id)"
        >
          <component :is="item.icon" :size="19" />
          <span>{{ item.title }}</span>
          <span v-if="page === item.id" class="nav-dot" />
        </button>
      </nav>
      <div class="sidebar-note">
        <Activity :size="19" /><strong>从评论到决策</strong>
        <p>理解消费者感知，<br />观察市场选择的变化。</p>
        <span class="tiny-label">LLM · PNS · BEAST</span>
      </div>
      <div class="sidebar-foot">
        <span class="online-dot" /> 本机研究版 <span class="mono">0.1</span>
      </div>
    </aside>

    <div class="workspace">
      <header class="topbar">
        <button
          class="icon-btn mobile-menu"
          aria-label="打开导航"
          @click="mobileNav = !mobileNav"
        >
          <Menu :size="22" />
        </button>
        <div class="breadcrumb">
          研究空间 <ChevronRight :size="14" /><strong>{{
            activePage.title
          }}</strong>
        </div>
        <div class="topbar-right">
          <span class="environment">阶段一 · 数据与准则</span>
          <span class="avatar" aria-label="本地研究人员">研</span>
        </div>
      </header>

      <main id="main-content">
        <div class="heading-row">
          <div>
            <p class="eyebrow">NEW ENERGY VEHICLE / DECISION SCIENCE</p>
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

        <div class="context-bar">
          <label class="project-control">
            <span>分析项目</span>
            <select
              v-model="projectId"
              aria-label="分析项目"
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
          <span v-if="overview" :class="['badge', isPreset ? 'teal' : 'blue']">
            {{ isPreset ? "预置准则模式" : "自定义准则模式" }}
          </span>
          <label
            v-if="overview && page !== 'criteria' && page !== 'experiments'"
            class="month-control"
          >
            <span>观察月份</span>
            <select
              v-model="month"
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
        </div>

        <div v-if="error" class="notice error" role="alert">
          <span>{{ error }}</span
          ><button class="text-button" @click="loadWorkspace">重新加载</button>
        </div>
        <div v-if="busy" class="loading-line" role="status">
          正在读取研究数据…
        </div>

        <template v-if="overview">
          <OverviewView v-if="page === 'overview'" />
          <DataView v-else-if="page === 'data'" />
          <CriteriaView v-else-if="page === 'criteria'" />
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
      @cancel.prevent="closeCreate"
    >
      <form @submit.prevent="createProject">
        <div class="dialog-heading">
          <div>
            <p class="eyebrow">NEW RESEARCH</p>
            <h2>建立分析项目</h2>
          </div>
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
            v-model="projectName"
            required
            maxlength="100"
            autofocus
            placeholder="例如：纯电轿车用户评价研究"
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
