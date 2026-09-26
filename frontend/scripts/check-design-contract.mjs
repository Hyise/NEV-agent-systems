import { existsSync, readFileSync } from "node:fs";
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

const styleLayers = [
  "./styles/foundation.css",
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
expectContains("src/App.vue", [
  "<AppBrand",
  'href="#main-content"',
  "aria-current=\"page === item.id ? 'page' : undefined\"",
  'class="evidence-rail"',
  'class="app-sidebar"',
  'class="app-header"',
]);
expectContains("src/Chart.vue", [
  "animation: false",
  "aria:",
  "ResizeObserver",
  "PingFang SC",
  "Bahnschrift",
]);
expectContains("src/views/OverviewView.vue", [
  'class="metric-strip"',
  'class="analysis-grid"',
  'class="panel research-note"',
  "消费者关注什么",
  "当前权重最高的三个准则",
  "研究流程",
  "overview.notes[0]",
]);
expectContains("src/styles/pages.css", [
  ".metric-strip",
  ".analysis-grid",
  ".research-note",
]);
expectContains("src/styles/components.css", [".empty", ".panel", ".notice"]);
expectContains("src/views/DataView.vue", [
  'class="panel data-workspace"',
  "dataset-toolbar",
  "搜索车型",
  "份额分母固定为当月全部入选车型",
  "导入加工数据",
  "导出CSV",
  "pagination",
]);
expectContains("src/views/CriteriaView.vue", [
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
expectContains("src/views/ScenarioView.vue", [
  'class="panel scenario-workspace"',
  "analysis-controls",
  "曲线类型",
  "curve-filters",
  "查看曲线对应数值",
  "选择至少一个准则",
]);
expectContains("src/views/SharesView.vue", [
  'class="shares-workspace"',
  "source-status",
  "筛选仅影响显示，不重新归一化",
  "真实样本份额",
  "归档模型估计",
  "delta-label",
]);
expectContains("src/views/ExperimentsView.vue", [
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

if (failures.length > 0) {
  console.error(
    "Design contract failed:\n" +
      failures.map((item) => `- ${item}`).join("\n"),
  );
  process.exit(1);
}

console.log("Design contract passed.");
