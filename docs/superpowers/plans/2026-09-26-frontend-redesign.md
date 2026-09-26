# 观衡前端重设计实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变数据、API 和研究口径的前提下，将现有六页 Vue 工作台重设计为领域化的机构式新能源汽车科研工作台。

**Architecture:** 保留 `App.vue → views → workspace/api` 的现有依赖方向，只重构展示层。`style.css` 变为四层 CSS 入口，新增一个无业务状态的 `AppBrand.vue`；通过无依赖的静态设计契约、TypeScript/构建门禁和真实浏览器回归共同约束视觉实现。

**Tech Stack:** Vue 3.5.22、TypeScript 5.9.3、Vite 7.1.9、ECharts 6.0.0、Lucide Vue、CSS、Node.js 内置模块、Playwright CLI。

**Spec:** `docs/superpowers/specs/2026-09-26-frontend-redesign-design.md`

## Global Constraints

- 不修改后端 API、SQLite schema、研究归档、算法逻辑、份额分母、准则版本、月份或实验结论口径。
- 不修改 `frontend/src/workspace.ts` 和 `frontend/src/api.ts`；若视觉实现必须改变其接口，停止执行并先修订规格。
- 不引入 PrimeVue、Tailwind、GSAP、外部字体或任何新的运行/开发依赖。
- 保留六个页面、项目/月/版本切换、新建项目、准则编辑、导入导出和现有错误处理行为。
- 使用规格中的六项核心色值；评论/准则为青色语义，销量/市场为橙色语义，不复制参考项目的院校资产。
- `App.vue` 只负责应用壳与装配；业务图表 option 留在 view；ECharts 生命周期继续由 `Chart.vue` 独占。
- 每个阶段必须通过 `format:check`、`typecheck`、`build` 和对应设计契约；视觉变更另做真实浏览器检查。
- 所有截图保存到已忽略的 `output/playwright/` 或 `.playwright-cli/`，不得提交浏览器产物。

## Review Focus

- 390px 窄屏：页面本身不得水平溢出，只有数据表容器允许局部横向滚动；Task 6 用浏览器尺寸和滚动宽度检查固定。
- 长项目名、长准则名和长等级文本：必须截断、换行或扩展而不覆盖操作；Task 4 用自定义项目和长文本浏览器场景固定。
- 加载、错误、空结果：结构不能坍塌，旧数据不能伪装成最新结果；Tasks 3–5 分页检查，Task 6 汇总回归。
- 图表无数据、筛选到零项和容器缩放：必须显示可行动空状态且没有控制台异常；Tasks 3、5 用浏览器场景固定。
- 键盘与减少动效：导航、对话框、按钮和焦点恢复可操作，`prefers-reduced-motion` 下无非必要位移；Tasks 2、4、6 固定。

---

### Task 1: 建立样式边界与可执行设计契约

**Files:**
- Create: `frontend/scripts/check-design-contract.mjs`
- Create: `frontend/src/styles/foundation.css`
- Create: `frontend/src/styles/shell.css`
- Create: `frontend/src/styles/components.css`
- Create: `frontend/src/styles/pages.css`
- Modify: `frontend/src/style.css`
- Modify: `frontend/package.json`

**Interfaces:**
- Consumes: 当前 `style.css` 的全部有效选择器和 `main.ts` 的现有样式入口。
- Produces: `npm.cmd run check:design`；固定顺序的四层 CSS 导入；后续任务可按职责修改的样式边界。

- [ ] **Step 1: 写失败的样式结构契约**

在 `check-design-contract.mjs` 使用 `node:fs`/`node:path`，添加 `read(relativePath)`、`expectContains(file, values)`、`expectNotContains(file, values)` 和统一失败汇总。首组断言要求 `style.css` 按顺序且只导入 `foundation.css`、`shell.css`、`components.css`、`pages.css`，并要求四个文件存在。

- [ ] **Step 2: 运行契约并确认 RED**

Run: `Set-Location frontend; node scripts/check-design-contract.mjs`

Expected: FAIL，报告缺少四个样式文件或入口导入。

- [ ] **Step 3: 无视觉变化地拆分现有样式**

按所有权迁移：令牌/reset/排版/辅助类进入 `foundation.css`；应用壳/导航/顶栏/全局对话框进入 `shell.css`；按钮/输入/徽章/提示/面板/表格进入 `components.css`；指标带、图表布局、准则、流程和页面特例进入 `pages.css`。`style.css` 只保留四条 `@import`。

- [ ] **Step 4: 将设计契约加入 npm 门禁**

在 `package.json` 添加 `"check:design": "node scripts/check-design-contract.mjs"`，并让 `format`/`format:check` 覆盖 `scripts` 与 `src/styles`，不新增依赖。

- [ ] **Step 5: 验证结构和行为基线**

Run: `npm.cmd run check:design; npm.cmd run format:check; npm.cmd run typecheck; npm.cmd run build`

Expected: 全部退出 0。启动系统并在 1440×1000 截取研究总览，与拆分前截图比较；布局、交互和文案不得发生有意变化。

- [ ] **Step 6: 提交**

```powershell
git add frontend/package.json frontend/scripts frontend/src/style.css frontend/src/styles
git commit -m "refactor(frontend): 拆分样式职责并建立设计契约"
```

### Task 2: 重设计应用壳与品牌导航

**Files:**
- Create: `frontend/src/components/AppBrand.vue`
- Modify: `frontend/scripts/check-design-contract.mjs`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/styles/foundation.css`
- Modify: `frontend/src/styles/shell.css`
- Modify: `frontend/src/styles/components.css`

**Interfaces:**
- Consumes: Task 1 的四层样式入口和现有 `createWorkspace()` 返回值。
- Produces: `AppBrand` 的 `compact?: boolean` 属性；`.app-shell`、`.app-sidebar`、`.app-header`、`.context-bar` 和 `.evidence-rail` 壳层契约。

- [ ] **Step 1: 扩展契约并确认 RED**

断言六个核心颜色值、三类字体变量、`prefers-reduced-motion`、`AppBrand.vue`、`App.vue` 中的 `<AppBrand`、跳到主内容链接、`aria-current` 和证据链轨道类均存在。

Run: `npm.cmd run check:design`

Expected: FAIL，首先报告缺少 `AppBrand.vue` 或新壳层标记。

- [ ] **Step 2: 实现 `AppBrand.vue`**

组件只接收 `compact?: boolean`，渲染“观衡”、`NEV DECISION RESEARCH` 和抽象数据刻度图形；图形使用内联语义无关 SVG 或 CSS，不引入图片资产，不读取 workspace。

- [ ] **Step 3: 重组 `App.vue` 壳层模板**

保留所有现有事件和状态绑定，将侧栏、项目简报、六项导航、顶栏、页面标题、上下文控制条、状态提示和新建项目对话框映射到 Task 2 产出的类名。导航继续使用异步页面组件、`aria-current` 和移动开关。

- [ ] **Step 4: 实现视觉令牌和壳层样式**

在 `foundation.css` 写入规格固定色值和字体角色；在 `shell.css` 实现 232px 浅色侧栏、64px 顶栏、双色证据链轨道、内容最大宽度及桌面导航状态；在 `components.css` 更新全局对话框与状态提示以适配新表面。

- [ ] **Step 5: 验证应用壳**

Run: `npm.cmd run check:design; npm.cmd run format:check; npm.cmd run typecheck; npm.cmd run build`

Browser: 1440px 检查完整侧栏与上下文条；1024px 检查窄侧栏；键盘从跳转链接进入主内容并遍历导航；打开/关闭新建项目对话框后焦点回到触发按钮。

Expected: 命令全部通过；导航和对话框行为与重设计前一致，无控制台异常。

- [ ] **Step 6: 提交**

```powershell
git add frontend/src/components/AppBrand.vue frontend/src/App.vue frontend/src/styles frontend/scripts/check-design-contract.mjs
git commit -m "feat(frontend): 重设计研究工作台应用壳"
```

### Task 3: 统一通用组件并重设计研究总览

**Files:**
- Modify: `frontend/scripts/check-design-contract.mjs`
- Modify: `frontend/src/Chart.vue`
- Modify: `frontend/src/views/OverviewView.vue`
- Modify: `frontend/src/styles/components.css`
- Modify: `frontend/src/styles/pages.css`

**Interfaces:**
- Consumes: Task 2 的令牌、壳层和现有 `useWorkspace()` 数据。
- Produces: 面板、按钮、输入、徽章、提示、表格、指标带和图表的共享视觉语义；`Chart` 的 props 仍为 `option`、`label`、`height?`。

- [ ] **Step 1: 扩展总览和图表契约并确认 RED**

断言 `Chart.vue` 使用统一字体/ARIA/无动画设置；总览保留四项指标、权重图、前三准则、来源说明和研究流程；样式存在 `.metric-strip`、`.analysis-grid`、`.research-note` 和空状态规则。

Run: `npm.cmd run check:design`

Expected: FAIL，报告缺少新总览类或图表令牌。

- [ ] **Step 2: 统一共享展示控件**

在 `components.css` 按规格实现低阴影面板、主/次/文本按钮、输入、选择、徽章、提示、空状态、表格和分页。保留现有 class API，避免为纯样式新增 Vue 包装组件。

- [ ] **Step 3: 更新 `Chart.vue`**

使用正文与数据字体回退链、结构线网格、青/橙序列和可读 tooltip；保留 `animation: false`、`ResizeObserver`、深度 watch、ARIA 和销毁逻辑。

- [ ] **Step 4: 重组 `OverviewView.vue`**

四项统计变为连续指标带；权重图和本月观察组成 2:1 主次布局；来源、导出和研究限制贴近相关内容。不得改变 `sortedWeights`、`topCriteria`、`download()` 或 `navigate()` 调用。

- [ ] **Step 5: 验证正常、空数据和缩放状态**

Run: `npm.cmd run check:design; npm.cmd run format:check; npm.cmd run typecheck; npm.cmd run build`

Browser: 在 1440px 和 1024px 查看总览；切换自定义空项目检查无权重状态；调整窗口后图表自动 resize；检查控制台和图表可访问名称。

Expected: 全部通过，空状态可行动，旧图不覆盖新项目。

- [ ] **Step 6: 提交**

```powershell
git add frontend/src/Chart.vue frontend/src/views/OverviewView.vue frontend/src/styles frontend/scripts/check-design-contract.mjs
git commit -m "feat(frontend): 统一分析组件与研究总览"
```

### Task 4: 重设计数据中心与准则工作台

**Files:**
- Modify: `frontend/scripts/check-design-contract.mjs`
- Modify: `frontend/src/views/DataView.vue`
- Modify: `frontend/src/views/CriteriaView.vue`
- Modify: `frontend/src/styles/pages.css`
- Modify: `frontend/src/styles/components.css`

**Interfaces:**
- Consumes: Tasks 2–3 的应用壳、控件样式和现有 workspace 方法。
- Produces: `.data-workspace`、`.criteria-workspace`、`.dataset-toolbar`、`.criteria-row` 的页面契约；不产生新的共享状态接口。

- [ ] **Step 1: 扩展数据/准则契约并确认 RED**

断言数据页仍包含搜索、分母说明、导入/导出和分页；准则页仍包含版本、草稿/冻结状态、等级数、保存、冻结和派生操作；要求新页面根类和表格/编辑列表类存在。

Run: `npm.cmd run check:design`

Expected: FAIL，报告缺少两个页面根类或工具条类。

- [ ] **Step 2: 重组 `DataView.vue`**

把数据集名称、记录数和文件操作组织为页内标题栏；搜索与口径说明合并为工具条；保留表格列、数字格式、搜索防抖、分页边界和导入行为。

- [ ] **Step 3: 重组 `CriteriaView.vue`**

把版本选择、状态与保存操作放入面板头；保持编辑态和只读态相同列结构；长名称和等级允许换行，删除按钮保持可访问名称，冻结/派生路径不变。

- [ ] **Step 4: 验证长文本、窄屏和编辑保护**

Run: `npm.cmd run check:design; npm.cmd run format:check; npm.cmd run typecheck; npm.cmd run build`

Browser: 使用自定义项目填入长准则名和长等级文本；检查 1024px/390px 不覆盖操作；制造未保存更改并切换项目，确认现有保护仍工作；打开导入并检查错误提示布局。

Expected: 全部通过；页面无整体横向滚动，数据表仅在自身容器滚动。

- [ ] **Step 5: 提交**

```powershell
git add frontend/src/views/DataView.vue frontend/src/views/CriteriaView.vue frontend/src/styles frontend/scripts/check-design-contract.mjs
git commit -m "feat(frontend): 重设计数据与准则工作区"
```

### Task 5: 重设计情景、份额与实验分析

**Files:**
- Modify: `frontend/scripts/check-design-contract.mjs`
- Modify: `frontend/src/views/ScenarioView.vue`
- Modify: `frontend/src/views/SharesView.vue`
- Modify: `frontend/src/views/ExperimentsView.vue`
- Modify: `frontend/src/styles/pages.css`

**Interfaces:**
- Consumes: Task 3 的 Chart/控件视觉语义和现有 `selectedCurves`、`predictions`、`experiments`。
- Produces: 三个分析页面的一致工具条、图表画布、来源状态和指标表格；不改变业务 option 的数据来源。

- [ ] **Step 1: 扩展分析页面契约并确认 RED**

断言情景页保留曲线类型、准则筛选、图表和折叠数据；份额页保留搜索、分母说明、图表、正负差值符号；实验页保留基线/消融、三项指标和研究限制。要求三个页面的新根类和来源状态类。

Run: `npm.cmd run check:design`

Expected: FAIL，报告缺少分析工作区类。

- [ ] **Step 2: 重组 `ScenarioView.vue`**

将分段选择、准则筛选和图例组织为分析控制区；图表为主要画布，说明和折叠数据紧随其后；关闭全部准则时显示可行动空状态。

- [ ] **Step 3: 重组 `SharesView.vue`**

图表与表格保持相同车型顺序；真实/估计份额沿用一致系列颜色；差值同时显示正负符号和文字/数值，不只用颜色；搜索口径保持可见。

- [ ] **Step 4: 重组 `ExperimentsView.vue`**

基线与消融共享表头和数值格式；BEAST 高亮使用字重、左侧标记和背景共同表达；来源及训练测试重叠限制置于表格前。

- [ ] **Step 5: 验证图表和空状态**

Run: `npm.cmd run check:design; npm.cmd run format:check; npm.cmd run typecheck; npm.cmd run build`

Browser: 检查三页在 1440px/1024px；筛选到零条车型、取消全部曲线、访问无实验数据的自定义项目；检查图表 resize、ARIA、控制台和网络请求。

Expected: 全部通过，来源和限制没有因重设计弱化。

- [ ] **Step 6: 提交**

```powershell
git add frontend/src/views/ScenarioView.vue frontend/src/views/SharesView.vue frontend/src/views/ExperimentsView.vue frontend/src/styles frontend/scripts/check-design-contract.mjs
git commit -m "feat(frontend): 重设计情景份额与实验分析"
```

### Task 6: 响应式、可访问性、文档与全量验收

**Files:**
- Modify: `frontend/scripts/check-design-contract.mjs`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/styles/foundation.css`
- Modify: `frontend/src/styles/shell.css`
- Modify: `frontend/src/styles/components.css`
- Modify: `frontend/src/styles/pages.css`
- Create: `docs/前端重设计验收记录.md`
- Modify: `README.md`
- Modify: `docs/代码审查记录.md`

**Interfaces:**
- Consumes: Tasks 1–5 的全部页面和样式契约。
- Produces: 1440/1024/390 三档最终响应式行为、完整验收证据和用户可发现的文档入口。

- [ ] **Step 1: 完成最终契约的 RED 扩展**

断言样式包含 1199/767 响应式边界、减少动效、可见焦点、抽屉遮罩、表格局部滚动和整页防溢出规则；断言 App 保留 skip link、移动导航开关和对话框可访问属性。

Run: `npm.cmd run check:design`

Expected: 若前序任务尚未覆盖任一最终规则则 FAIL，并列出缺失规则。

- [ ] **Step 2: 完成三档响应式和交互收口**

补齐 232px 桌面侧栏、平板压缩布局、手机抽屉/单列布局；确保抽屉关闭后焦点回到触发按钮，数据表之外 `documentElement.scrollWidth === innerWidth`。

- [ ] **Step 3: 完成键盘、减少动效和对比度检查**

从跳转链接遍历导航、项目/月选择、页面主要操作和对话框；启用 reduced motion 确认无位移动画；检查青/橙状态均有文字或图形辅助。

- [ ] **Step 4: 执行全量自动化门禁**

Run:

```powershell
& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend\tests -q --basetemp .pytest-tmp-final
Set-Location frontend
npm.cmd run check:design
npm.cmd run format:check
npm.cmd run typecheck
npm.cmd run build
```

Expected: 后端现有 25 项测试通过；四项前端命令退出 0。记录但不以提高阈值隐藏现有 ECharts chunk 提示。

- [ ] **Step 5: 执行完整浏览器矩阵**

在 1440×1000、1024×768、390×844 依次走查六页、项目/月切换、新建项目、准则保存/冻结/派生、搜索、分页、导入和导出；收集截图，检查控制台和关键请求。随后启用 reduced motion 再走查导航和对话框。

Expected: 没有未处理异常、意外 404/500、整页横向滚动或阻断流程的视觉问题。

- [ ] **Step 6: 写验收与审查文档**

`docs/前端重设计验收记录.md` 记录视口、流程、命令、截图路径、已知提示和未覆盖项；README 增加入口；`docs/代码审查记录.md` 记录样式边界、未改数据层和遗留性能提示。

- [ ] **Step 7: 提交**

```powershell
git add frontend README.md docs/前端重设计验收记录.md docs/代码审查记录.md
git commit -m "docs(frontend): 记录重设计验收结果"
```

### Task 7: 分支级审查与交付

**Files:**
- Modify: 仅审查发现且属于本规格范围的文件

**Interfaces:**
- Consumes: Tasks 1–6 的全部提交与验收证据。
- Produces: 无 Critical/Important 未解决项的可合并分支。

- [ ] **Step 1: 对照规格逐条审查**

确认十个规格章节均有实现或验证证据；检查 `workspace.ts`、`api.ts`、后端和研究数据没有意外变化。

- [ ] **Step 2: 审查差异与文件边界**

Run: `git diff --check main...HEAD; git diff --stat main...HEAD; git status --short`

Expected: 无空白错误；只包含批准的前端和文档文件；工作区干净。

- [ ] **Step 3: 修复审查发现并重跑对应门禁**

Critical 和 Important 必须在交付前修复；Minor 只有在不会扩大范围时处理，否则写入验收记录。

- [ ] **Step 4: 推送分支并交付审核**

Run: `git push origin feature/frontend-redesign`

Expected: 远端分支更新成功，本地 HEAD 与远端提交号一致；由用户决定合并方式。
