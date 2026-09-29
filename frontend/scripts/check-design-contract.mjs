import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const failures = [];

function read(relativePath) {
  const absolutePath = resolve(frontendRoot, relativePath);
  if (!existsSync(absolutePath)) {
    failures.push(`${relativePath}: file is missing`);
    return "";
  }
  return readFileSync(absolutePath, "utf8");
}

function expectContains(relativePath, values) {
  const content = read(relativePath);
  for (const value of values) {
    if (!content.includes(value)) {
      failures.push(
        `${relativePath}: expected to contain ${JSON.stringify(value)}`,
      );
    }
  }
}

function expectNotContains(relativePath, values) {
  const content = read(relativePath);
  for (const value of values) {
    if (content.includes(value)) {
      failures.push(
        `${relativePath}: expected not to contain ${JSON.stringify(value)}`,
      );
    }
  }
}

function sourceFiles(relativeDirectory) {
  const absoluteDirectory = resolve(frontendRoot, relativeDirectory);
  if (!existsSync(absoluteDirectory)) return [];
  return readdirSync(absoluteDirectory, { withFileTypes: true }).flatMap(
    (entry) => {
      const relativePath = `${relativeDirectory}/${entry.name}`;
      if (entry.isDirectory()) return sourceFiles(relativePath);
      return /\.(ts|vue)$/.test(entry.name) ? [relativePath] : [];
    },
  );
}

const styleLayers = [
  "./styles/foundation.css",
  "./styles/platform.css",
  "./styles/shell.css",
  "./styles/components.css",
  "./styles/pages.css",
];

const entryPath = "src/style.css";
const entry = read(entryPath);
let previousIndex = -1;

for (const layer of styleLayers) {
  const importStatement = `@import \"${layer}\";`;
  const index = entry.indexOf(importStatement);
  if (index === -1) {
    failures.push(`${entryPath}: missing ${importStatement}`);
  } else if (index < previousIndex) {
    failures.push(`${entryPath}: imports must follow the declared layer order`);
  }
  previousIndex = index;
  read(`src/${layer.slice(2)}`);
}

expectNotContains(entryPath, [":root {", ".app-shell {", ".panel {"]);
expectContains("package.json", [
  '"check:design": "node scripts/check-design-contract.mjs"',
]);
expectContains("src/main.ts", [
  "createWebHashHistory",
  "createPlatformRouter",
  ".use(router)",
]);
expectContains("src/App.vue", [
  "<RouterView",
  "<KeepAlive",
  "router.onError",
  "模块加载失败",
  "重新加载",
  "返回平台",
]);
expectContains("src/platform/PlatformHome.vue", [
  "观衡研究平台",
  "researchModules",
  "<RouterLink",
]);
expectContains("src/platform/AdaptiveIntroduction.vue", [
  "自适应评估系统",
  "研究材料待接入",
  "业务口径待确认",
  "后续功能建设",
  "返回研究平台",
]);
expectNotContains("src/platform/AdaptiveIntroduction.vue", [
  "开始评估",
  "<form",
  '"/api',
]);
expectContains("src/styles/foundation.css", [
  "#f3f5f6",
  "#ffffff",
  "#1e2b38",
  "#d9e0e5",
  "#0f7c82",
  "#c65a3a",
  "--font-display",
  "--font-body",
  "--font-data",
  "prefers-reduced-motion",
]);
read("src/components/AppBrand.vue");
const mcdmShellPath = "src/modules/mcdm/McdmWorkbench.vue";
expectContains(mcdmShellPath, [
  "<AppBrand",
  'href="#main-content"',
  'class="mcdm-shell"',
  'class="mcdm-platform-bar"',
  'class="research-context"',
  'to="/"',
  "返回研究平台",
  "研究准备",
  "分析复核",
  ':title="currentProjectName"',
  "aria-current=\"page === item.id ? 'page' : undefined\"",
  'class="app-sidebar"',
]);
expectNotContains(mcdmShellPath, [
  "NEW ENERGY VEHICLE",
  "NEW RESEARCH",
  'class="evidence-rail"',
  "阶段一 · 数据与准则",
  '<component :is="item.icon"',
  "icon: LayoutDashboard",
]);
expectContains("src/components/BaseChart.vue", [
  "animation: false",
  "aria:",
  "ResizeObserver",
  "SimSun",
  "宋体",
]);
expectNotContains("src/components/BaseChart.vue", [
  "PingFang SC",
  "Bahnschrift",
]);
expectContains("src/modules/mcdm/views/OverviewView.vue", [
  'class="metric-strip"',
  'class="overview-evidence"',
  'class="overview-evidence__summary"',
  'class="research-process"',
  "消费者关注什么",
  "当前权重最高的三个准则",
  "研究流程",
  "overview.notes[0]",
]);
expectNotContains("src/modules/mcdm/views/OverviewView.vue", [
  'class="analysis-grid"',
  "RESEARCH NOTES",
]);
expectContains("src/styles/pages.css", [
  ".metric-strip",
  ".overview-evidence",
  ".overview-evidence__summary",
  ".research-process",
]);
expectContains("src/styles/components.css", [".empty", ".panel", ".notice"]);
expectContains("src/modules/mcdm/views/DataView.vue", [
  'class="data-workspace"',
  'class="data-command-bar"',
  'class="dataset-filter-bar"',
  'class="data-table-region"',
  "dataset-toolbar",
  "搜索车型",
  "份额分母固定为当月全部入选车型",
  "导入加工数据",
  "导出CSV",
  "pagination",
]);
expectNotContains("src/modules/mcdm/views/DataView.vue", [
  'class="panel data-workspace"',
]);
expectContains("src/modules/mcdm/views/CriteriaView.vue", [
  'class="criteria-workspace"',
  "criteria-row",
  "版本",
  "草稿可编辑",
  "已冻结",
  "保存草稿",
  "保存并冻结",
  "派生新版本",
]);
expectContains("src/styles/pages.css", [
  ".data-workspace",
  ".dataset-toolbar",
  ".criteria-workspace",
  ".criteria-row",
]);
expectContains("src/modules/mcdm/views/ScenarioView.vue", [
  'class="panel scenario-workspace"',
  "analysis-controls",
  "曲线类型",
  "curve-filters",
  "查看曲线对应数值",
  "选择至少一个准则",
]);
expectContains("src/modules/mcdm/views/SharesView.vue", [
  'class="shares-workspace"',
  "source-status",
  "筛选仅影响显示，不重新归一化",
  "真实样本份额",
  "归档模型估计",
  "delta-label",
]);
expectContains("src/modules/mcdm/views/ExperimentsView.vue", [
  'class="experiments-workspace"',
  "source-status",
  "基线模型比较",
  "消融实验",
  "R² ↑",
  "WAPE ↓",
  "RMSE ↓",
  "训练",
]);
expectContains("src/styles/pages.css", [
  ".scenario-workspace",
  ".shares-workspace",
  ".experiments-workspace",
  ".source-status",
  ".delta-label",
]);
expectContains("src/styles/foundation.css", [
  "overflow-x: clip",
  ":focus-visible",
  "prefers-reduced-motion",
  "SimSun",
  "宋体",
]);
expectContains("src/styles/shell.css", [
  "@media (max-width: 1199px)",
  "@media (max-width: 767px)",
  ".nav-backdrop",
]);
expectContains("src/styles/components.css", [
  ".table-scroll",
  "overflow-x: auto",
]);
expectContains(mcdmShellPath, [
  ':aria-expanded="mobileNav"',
  'aria-controls="primary-navigation"',
  'aria-labelledby="create-project-title"',
  'id="create-project-title"',
]);
const workspaceOwners = sourceFiles("src").filter((relativePath) =>
  read(relativePath).includes("const workspace = createWorkspace();"),
);
if (workspaceOwners.length !== 1 || workspaceOwners[0] !== mcdmShellPath) {
  failures.push(
    `${mcdmShellPath}: must be the only createWorkspace() owner; found ${workspaceOwners.join(", ") || "none"}`,
  );
}
for (const boundaryPath of ["src/platform/modules.ts", "src/router/index.ts"]) {
  expectNotContains(boundaryPath, [
    "modules/mcdm/workspace",
    "modules/mcdm/api",
  ]);
}
expectContains("../启动观衡网站.cmd", [
  "scripts\\start-site.ps1",
  "ExecutionPolicy Bypass",
]);
expectContains("../停止观衡网站.cmd", ["scripts\\stop-local.ps1"]);
expectContains("../scripts/start-site.ps1", [
  "start-local.ps1",
  "Start-Process",
  "NoBrowser",
  "npm.cmd",
]);

if (failures.length > 0) {
  console.error(
    "Design contract failed:\n" +
      failures.map((item) => `- ${item}`).join("\n"),
  );
  process.exit(1);
}

console.log("Design contract passed.");
