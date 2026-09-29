# 观衡双研究系统平台实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变现有多准则研究口径和后端接口的前提下，建立双研究系统入口、隔离多准则模块，并把现有工作台优化为克制、清晰的科研工具界面。

**Architecture:** 使用 Vue Router Hash 路由建立平台层，只在进入 `/#/mcdm` 时创建多准则 workspace；平台入口和 `/#/adaptive` 规划页不读取研究 API。先机械迁移现有多准则代码并验证行为不变，再分别实现平台入口、工作台壳层和六个业务页面的视觉优化。

**Tech Stack:** Vue 3.5.22、TypeScript 5.9.3、Vite 7.1.9、Vue Router 4、Vitest、ECharts 6.0.0、Lucide Vue、CSS、Playwright CLI、FastAPI。

**Spec:** `docs/superpowers/specs/2026-09-29-dual-research-platform-design.md`

## Global Constraints

- 根地址进入平台入口；多准则系统使用 `/#/mcdm`，自适应规划页使用 `/#/adaptive`，未知地址回退到 `/#/`。
- 自适应评估本阶段只展示规划状态，不建立业务模型、API、Store、图表、表单或模拟数据。
- 不修改后端 API、SQLite schema、研究归档、算法、份额分母、实验数值或研究限制。
- 平台入口和自适应规划页不得发送多准则 API 请求；workspace 只在首次进入多准则模块时创建。
- `vue-router` 是唯一新增运行依赖；允许新增 Vitest 作为测试开发依赖，不引入微前端、组件库、网络字体或动画库。
- 标题、正文、控件、数据和 ECharts 继续使用 `SimSun, "宋体", STSong, "Songti SC", serif` 回退链。
- 不使用渐变、玻璃拟态、大面积阴影、圆角卡片墙、无意义科技连线或循环装饰动画。
- 多准则模块只使用 `#235F68` 作为模块识别色，自适应规划页使用 `#625C82`；错误、警告和成功使用独立语义色。
- 保留项目/月/版本切换、未保存准则保护、数据导入导出、图表、实验档案和现有错误处理行为。
- 每个任务提交前执行该任务列出的门禁；浏览器产物只保存到已忽略的 `output/playwright/`。

## Review Focus

- 直接刷新 `/#/mcdm`、浏览器后退/前进和未知 Hash：必须进入正确页面且不出现白屏；由 Task 1 路由单元测试和 Task 8 浏览器回归固定。
- 平台入口或自适应规划页在 API 不可用时：仍须正常显示且不能请求 `/api/projects`；由 Task 3 网络断言固定。
- 多准则准则草稿存在未保存修改时返回平台再进入：草稿必须仍在，项目和版本保护仍有效；由 Task 4 浏览器场景固定。
- 长项目名、长准则名和 390px 窄屏：文字不得覆盖操作，页面本身不得横向溢出；由 Tasks 4、6、8 固定。
- 异步模块加载失败或业务数据为空：必须提供可行动说明，不能显示空白页面或伪造旧数据；由 Tasks 3、5、7 固定。

---

### Task 1: 建立平台路由与模块注册契约

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/src/platform/modules.ts`
- Create: `frontend/src/router/index.ts`
- Create: `frontend/src/router/index.spec.ts`
- Create: `frontend/src/platform/modules.spec.ts`
- Create: `frontend/vitest.config.ts`

**Interfaces:**
- Produces: `ModuleId = "mcdm" | "adaptive"`；`ModuleStatus = "available" | "planned"`；`ResearchModule` 静态元数据类型；`researchModules: readonly ResearchModule[]`。
- Produces: `PlatformRouteComponents` 路由组件映射；`createPlatformRouter(history: RouterHistory, components: PlatformRouteComponents): Router`，生产环境传入 Hash history 和异步组件，测试传入 memory history 和无状态测试组件。
- Produces: 命名路由 `platform-home`、`mcdm`、`adaptive`，以及重定向到 `/` 的 catch-all。

- [ ] **Step 1: 安装被规格允许的依赖**

Run: `Set-Location frontend; npm.cmd install vue-router@4; npm.cmd install --save-dev vitest`

Expected: `package.json` 仅新增 `vue-router` 运行依赖、`vitest` 开发依赖和 `test` 脚本；锁文件同步更新。

- [ ] **Step 2: 写模块注册表和路由失败测试**

`modules.spec.ts` 断言两个模块 ID、状态、路径、操作文案和唯一性；`index.spec.ts` 使用 memory history 和三个无状态测试组件，断言 `/`、`/mcdm`、`/adaptive` 的命名路由、仅 MCDM 路由的 `meta.keepAlive === true`，以及 `/missing` 回退到 `/`。

- [ ] **Step 3: 运行单元测试并确认 RED**

Run: `npm.cmd test -- --run src/platform/modules.spec.ts src/router/index.spec.ts`

Expected: FAIL，报告 `modules.ts` 或 `router/index.ts` 不存在。

- [ ] **Step 4: 实现静态模块注册表和路由工厂**

`ResearchModule` 固定包含 `id`、`name`、`status`、`statusLabel`、`routeName`、`path`、`actionLabel`、`accent`；自适应模块元数据只能表达“规划中”和“查看系统规划”。路由工厂只消费传入的组件映射，不直接导入平台页面、workspace 或业务视图，从而允许本任务在页面迁移前独立构建。

- [ ] **Step 5: 配置 Vitest 并通过路由测试**

在 `vitest.config.ts` 配置 `environment: "node"`；运行 Task 1 两个测试、`typecheck` 和 `build`。

Expected: 测试全部 PASS，生产构建成功，当前页面行为尚未改变。

- [ ] **Step 6: 提交**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/src/platform frontend/src/router
git commit -m "feat(platform): 建立研究模块注册与路由契约"
```

### Task 2: 无视觉变化地隔离多准则模块

**Files:**
- Create: `frontend/src/modules/mcdm/McdmWorkbench.vue`
- Move: `frontend/src/workspace.ts` → `frontend/src/modules/mcdm/workspace.ts`
- Move: `frontend/src/api.ts` → `frontend/src/modules/mcdm/api.ts`
- Move: `frontend/src/views/*.vue` → `frontend/src/modules/mcdm/views/*.vue`
- Move: `frontend/src/Chart.vue` → `frontend/src/components/BaseChart.vue`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/scripts/check-design-contract.mjs`

**Interfaces:**
- Consumes: Task 1 的模块路由，但本任务暂不挂载路由。
- Produces: `McdmWorkbench.vue` 作为唯一 `createWorkspace()` / `provideWorkspace()` 调用点；现有 `Workspace`、`Page`、`useWorkspace()` 和 API 类型保持原签名。
- Produces: `BaseChart.vue` 继续只接收 `option`、`label`、`height?`。

- [ ] **Step 1: 扩展静态契约并确认 RED**

要求目标目录存在；要求 `McdmWorkbench.vue` 包含唯一 workspace 创建；禁止 `platform/` 和 `router/` 导入 `modules/mcdm/workspace` 或 `modules/mcdm/api`。

Run: `npm.cmd run check:design`

Expected: FAIL，报告目标模块文件缺失。

- [ ] **Step 2: 机械移动 API、workspace、六个视图和图表组件**

只修改 import 路径和组件名；不改变模板、业务状态、请求顺序或 CSS 类。使用 `git diff --color-moved` 检查移动内容没有混入行为修改。

- [ ] **Step 3: 提取 `McdmWorkbench.vue`**

将当前 `App.vue` 的脚本与模板原样迁入模块壳；临时 `App.vue` 只渲染 `<McdmWorkbench />`，确保本任务结束时页面与迁移前一致。

- [ ] **Step 4: 运行迁移门禁**

Run: `npm.cmd run check:design; npm.cmd test -- --run; npm.cmd run format:check; npm.cmd run typecheck; npm.cmd run build`

Browser: 在当前根地址检查六个页面、项目切换和控制台。

Expected: 全部退出 0；视觉和交互无有意变化；后端文件和研究数据无差异。

- [ ] **Step 5: 提交**

```powershell
git add frontend/src frontend/scripts/check-design-contract.mjs
git commit -m "refactor(frontend): 隔离多准则研究模块"
```

### Task 3: 实现研究平台入口与自适应规划页

**Files:**
- Modify: `frontend/src/main.ts`
- Modify: `frontend/src/App.vue`
- Create: `frontend/src/platform/PlatformHome.vue`
- Create: `frontend/src/platform/AdaptiveIntroduction.vue`
- Create: `frontend/src/styles/platform.css`
- Modify: `frontend/src/style.css`
- Modify: `frontend/src/styles/foundation.css`
- Modify: `frontend/scripts/check-design-contract.mjs`
- Test: `frontend/src/router/index.spec.ts`

**Interfaces:**
- Consumes: `researchModules` 和 `createPlatformRouter(history, components)`。
- Produces: 根组件 `<RouterView>`；`meta.keepAlive === true` 的多准则模块缓存；平台入口和自适应规划页的语义链接。

- [ ] **Step 1: 写入口与规划页失败契约**

断言 `main.ts` 安装 router；`App.vue` 使用 RouterView/KeepAlive；入口包含“多准则决策系统”“自适应评估系统”“进入多准则系统”“查看系统规划”；规划页包含“研究材料待接入”“业务口径待确认”“后续功能建设”，并禁止“开始评估”、表单和 `/api`。

- [ ] **Step 2: 运行契约并确认 RED**

Run: `npm.cmd run check:design`

Expected: FAIL，报告入口组件或路由挂载缺失。

- [ ] **Step 3: 挂载路由并实现平台语义结构**

`main.ts` 使用 `createWebHashHistory()` 和三个异步组件调用路由工厂。`App.vue` 只拥有 RouterView 和按 route meta 缓存的组件，不创建业务状态；在根组件注册 `router.onError`，用 `routeError: Ref<Error | null>` 控制模块加载失败提示，“重新加载”调用 `window.location.reload()`，“返回平台”清空错误并导航到 `/`。`PlatformHome.vue` 从注册表渲染两个模块入口；`AdaptiveIntroduction.vue` 只展示已确认状态和返回平台链接。

- [ ] **Step 4: 实现平台视觉系统**

入口使用无阴影双列目录和真实路径/建设路径；使用规格固定色值与宋体；小于 `768px` 改为纵向排列。异步模块错误边界提供“重新加载”和“返回平台”。

- [ ] **Step 5: 验证路由和无请求边界**

Run: `npm.cmd run check:design; npm.cmd test -- --run; npm.cmd run format:check; npm.cmd run typecheck; npm.cmd run build`

Browser: 新会话访问 `/`，记录网络请求；再进入 `/#/adaptive`。断言两个页面均没有 `/api/projects` 请求；未知 Hash 回到入口；键盘可访问两个入口。

- [ ] **Step 6: 提交**

```powershell
git add frontend/src frontend/scripts/check-design-contract.mjs
git commit -m "feat(platform): 增加双研究系统入口"
```

### Task 4: 重设计多准则工作台壳层

**Files:**
- Modify: `frontend/src/modules/mcdm/McdmWorkbench.vue`
- Modify: `frontend/src/styles/shell.css`
- Modify: `frontend/src/styles/components.css`
- Modify: `frontend/scripts/check-design-contract.mjs`

**Interfaces:**
- Consumes: 现有 `Workspace` 全部状态与动作，不改变其接口。
- Produces: 平台栏、约 `176px` 文字导航、研究上下文栏、返回平台链接和移动抽屉；业务 view 插槽保持现有条件渲染。

- [ ] **Step 1: 写壳层失败契约**

要求返回平台链接、研究准备/分析复核分组、`aria-current`、项目/月/版本上下文和移动抽屉；禁止 `NEW ENERGY VEHICLE`、`evidence-rail`、导航图标数组和重复阶段标签。

- [ ] **Step 2: 运行契约并确认 RED**

Run: `npm.cmd run check:design`

Expected: FAIL，报告旧壳层标记仍存在或新结构缺失。

- [ ] **Step 3: 重组壳层模板与状态展示**

保留现有事件绑定和禁用条件；项目/月/版本进入固定上下文栏；“新建研究”作为模块级操作；返回平台使用 RouterLink。导航仍调用现有 `navigate(page)`，不把六个业务页升级为独立路由。

- [ ] **Step 4: 实现克制壳层样式**

删除双色轨道、大面积当前项底色、冗余英文和长侧栏说明；用分隔线、字重和短竖线表达层级。长项目名截断但保留完整可访问名称。

- [ ] **Step 5: 验证状态保活和移动焦点**

Browser: 修改自定义准则但不保存，返回平台再进入多准则模块，断言草稿和禁用保护仍在；390px 打开/关闭抽屉并验证焦点恢复；检查项目、月份和版本切换。

Run: `npm.cmd run check:design; npm.cmd test -- --run; npm.cmd run format:check; npm.cmd run typecheck; npm.cmd run build`

- [ ] **Step 6: 提交**

```powershell
git add frontend/src/modules/mcdm/McdmWorkbench.vue frontend/src/styles frontend/scripts/check-design-contract.mjs
git commit -m "feat(frontend): 重设计多准则工作台壳层"
```

### Task 5: 优化研究总览与数据中心

**Files:**
- Modify: `frontend/src/modules/mcdm/views/OverviewView.vue`
- Modify: `frontend/src/modules/mcdm/views/DataView.vue`
- Modify: `frontend/src/styles/components.css`
- Modify: `frontend/src/styles/pages.css`
- Modify: `frontend/scripts/check-design-contract.mjs`

**Interfaces:**
- Consumes: 现有 overview/data workspace 字段和动作。
- Produces: 共用页面标题/工具区语义；总览证据区；以数据表为主体的数据中心。

- [ ] **Step 1: 写页面结构失败契约**

总览必须保留四项指标、权重、来源、导出和研究限制；数据中心必须保留搜索、分页、导入、导出、份额分母说明和空结果。契约禁止重新引入英文眉题和嵌套卡片结构。

- [ ] **Step 2: 运行契约并确认 RED**

Run: `npm.cmd run check:design`

Expected: FAIL，报告新证据区或工具区类缺失。

- [ ] **Step 3: 重组总览与数据中心**

总览使用紧凑指标行和一块主要权重证据区；数据中心把数据集信息、操作和搜索合为工具区，表格直接成为主内容。不得修改计算属性、下载、分页或搜索动作。

- [ ] **Step 4: 验证正常、空数据和错误状态**

Browser: 检查预置项目、无数据自定义项目、零搜索结果、分页和导出；图表无数据时显示可行动说明，旧数据不冒充最新结果。

Run: `npm.cmd run check:design; npm.cmd run format:check; npm.cmd run typecheck; npm.cmd run build`

- [ ] **Step 5: 提交**

```powershell
git add frontend/src/modules/mcdm/views/OverviewView.vue frontend/src/modules/mcdm/views/DataView.vue frontend/src/styles frontend/scripts/check-design-contract.mjs
git commit -m "feat(frontend): 优化总览与数据工作区"
```

### Task 6: 优化准则编辑工作区

**Files:**
- Modify: `frontend/src/modules/mcdm/views/CriteriaView.vue`
- Modify: `frontend/src/styles/pages.css`
- Modify: `frontend/scripts/check-design-contract.mjs`

**Interfaces:**
- Consumes: 现有草稿、冻结、派生、保存和脏状态动作。
- Produces: 文档式准则版本头、分隔线准则行和稳定的编辑/只读布局。

- [ ] **Step 1: 写准则工作区失败契约**

断言版本、草稿/冻结状态、保存、冻结、派生、撤销和等级顺序均保留；要求准则行使用分隔结构，禁止每条准则独立阴影或卡片。

- [ ] **Step 2: 运行契约并确认 RED**

Run: `npm.cmd run check:design`

Expected: FAIL，报告文档式工作区标记缺失。

- [ ] **Step 3: 重组模板和样式**

编辑态与只读态使用相同列结构；长名称和长等级允许换行且不覆盖删除/保存操作；危险操作不只依赖颜色表达。

- [ ] **Step 4: 验证完整准则流程**

Browser: 检查长文本、添加/删除等级、撤销、保存、冻结、派生和未保存保护；不提交仅用于布局的临时数据。

Run: `npm.cmd run check:design; npm.cmd run format:check; npm.cmd run typecheck; npm.cmd run build`

- [ ] **Step 5: 提交**

```powershell
git add frontend/src/modules/mcdm/views/CriteriaView.vue frontend/src/styles/pages.css frontend/scripts/check-design-contract.mjs
git commit -m "feat(frontend): 优化准则版本编辑器"
```

### Task 7: 优化情景、份额、实验与图表

**Files:**
- Modify: `frontend/src/components/BaseChart.vue`
- Modify: `frontend/src/modules/mcdm/views/ScenarioView.vue`
- Modify: `frontend/src/modules/mcdm/views/SharesView.vue`
- Modify: `frontend/src/modules/mcdm/views/ExperimentsView.vue`
- Modify: `frontend/src/styles/components.css`
- Modify: `frontend/src/styles/pages.css`
- Modify: `frontend/scripts/check-design-contract.mjs`

**Interfaces:**
- Consumes: 现有情景曲线、份额预测、实验归档数据与方法。
- Produces: 一致的图表文字/网格/提示框；分析控制区；统一实验表结构；保留 `BaseChart` props。

- [ ] **Step 1: 写分析页失败契约**

要求情景筛选、曲线空状态、份额分母、真实/估计顺序、高估/低估文字、实验限制和归档来源均保留；要求图表继续无动画、响应尺寸和 ARIA。

- [ ] **Step 2: 运行契约并确认 RED**

Run: `npm.cmd run check:design`

Expected: FAIL，报告新分析控制区或统一表结构缺失。

- [ ] **Step 3: 重组三个分析页面和图表视觉**

控制项放在图表上方；表格按需展开；真实/估计/差值阅读顺序不变；基线与消融共享列和数值格式。只改展示，不改 option 中的数据来源、排序和计算。

- [ ] **Step 4: 验证正常与空状态**

Browser: 情景曲线全取消、份额搜索为零、无预测月份和自定义项目无实验档案时均显示可行动说明；调整容器后图表 resize；控制台无异常。

Run: `npm.cmd run check:design; npm.cmd run format:check; npm.cmd run typecheck; npm.cmd run build`

- [ ] **Step 5: 提交**

```powershell
git add frontend/src/components/BaseChart.vue frontend/src/modules/mcdm/views frontend/src/styles frontend/scripts/check-design-contract.mjs
git commit -m "feat(frontend): 优化多准则分析页面"
```

### Task 8: 完成响应式、可访问性与分支级验收

**Files:**
- Modify: `frontend/src/styles/platform.css`
- Modify: `frontend/src/styles/shell.css`
- Modify: `frontend/src/styles/components.css`
- Modify: `frontend/src/styles/pages.css`
- Modify: `frontend/scripts/check-design-contract.mjs`
- Create: `docs/ADR/0001-双研究系统平台与模块路由.md`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/开发与架构规范.md`
- Modify: `docs/系统设计与实施路线.md`
- Modify: `docs/运行须知.md`
- Create: `docs/双研究系统平台验收记录.md`

**Interfaces:**
- Consumes: Tasks 1–7 全部页面、模块边界和设计令牌。
- Produces: 1440/1024/390 三档稳定布局、完整文档和可审核分支。

- [ ] **Step 1: 扩展最终设计契约并确认 RED**

断言三个断点、页面横向溢出保护、焦点样式、减少动效、宋体、固定色值、入口文案和模块隔离规则；断言旧路径文件不存在。

- [ ] **Step 2: 修复响应式和可访问性缺口**

在 `1199px` 和 `767px` 完成入口、壳层、上下文栏、图表、表格和准则编辑布局；补齐 aria-current、焦点恢复、触控尺寸和异步错误操作。

- [ ] **Step 3: 执行完整自动化门禁**

Run:

```powershell
E:\anaconda927\envs\py311\python.exe -m pytest backend\tests -q
Set-Location frontend
npm.cmd test -- --run
npm.cmd run check:design
npm.cmd run format:check
npm.cmd run typecheck
npm.cmd run build
```

Expected: 全部退出 0；后端仍为现有 25 项通过；仅允许记录而不隐藏 ECharts 大块提示。

- [ ] **Step 4: 执行真实浏览器矩阵**

在 1440×1000、1024×768、390×844 检查入口、两个模块页面、六个多准则页面、前进后退、刷新、长文本、空状态、错误状态、未保存草稿、键盘焦点和减少动效。记录 `scrollWidth === innerWidth`、控制台和网络结果，截图保存到 `output/playwright/`。

- [ ] **Step 5: 同步架构、运行与验收文档**

ADR 记录方案 A、顶部切换和微前端的取舍；AGENTS 明确自适应仅为入口/规划页；README 和运行须知说明启动后进入平台；验收记录写实际命令、结果、截图和已知边界，不写未执行证据。

- [ ] **Step 6: 提交文档与最终修复**

```powershell
git add frontend AGENTS.md README.md docs
git commit -m "docs(platform): 完成双研究系统平台验收"
```

- [ ] **Step 7: 分支级审查与交付**

Run: `git diff --check main...HEAD; git status --short; git diff --stat main...HEAD`

确认没有 Critical/Important 未解决项；`backend/`、研究归档和数据库无意外变化。用户授权后推送主题分支，保持 `main` 不变并交由用户决定合并。
