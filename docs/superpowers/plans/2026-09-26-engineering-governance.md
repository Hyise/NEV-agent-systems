# 工程化治理与项目级 Skill 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为观衡项目建立项目级 Skill、常驻编码约束和可持续维护的软件设计规范。

**Architecture:** 常驻且跨任务生效的规则写入根目录 `AGENTS.md`；具体工程流程由 `.agents/skills/` 下的项目级 Skill 按需触发；详细规范放入 `docs/`，Skill 和 `AGENTS.md` 只路由到与当前任务相关的文档。第三方 Skill 固定来源并保留原始内容，项目约束不直接修改第三方副本。

**Tech Stack:** Markdown、Agent Skills (`SKILL.md`)、Python 3.11、FastAPI 0.128.8、Pydantic 2.12.2、Vue 3.5.22、TypeScript 5.9.3、Vite 7.1.9、pytest、Playwright。

**Spec:** 用户已批准方案 A；候选和边界记录于本对话，项目现有架构见 `docs/系统设计与实施路线.md` 与 `docs/代码审查记录.md`。

## Global Constraints

- 所有新增 Skill 安装在项目内 `.agents/skills/`，不得修改全局 Skill 或其他项目。
- 已由 Codex 或插件提供的同名流程 Skill 不复制到项目，避免重复发现和触发冲突。
- 仅下载 `security-best-practices`、`security-threat-model`、FastAPI 官方 Skill；Vue 规则使用项目专用轻量 Skill。
- 第三方 Skill 视为特权指令，安装后必须检查文件清单、`SKILL.md`、脚本和外部依赖。
- 项目锁定 FastAPI 0.128.8；FastAPI Skill 的新特性不得绕过版本核验直接进入代码。
- 文档使用中文说明，代码标识、命令和路径保持原始形式。
- 本次不修改产品业务行为，不新增运行依赖，不删除现有文件。

## Review Focus

- 同名 Skill 重复：项目级 Skill 不得复制已有全局流程 Skill，避免发现顺序不确定。
- 第三方指令风险：下载后的 Skill 不得包含未说明的联网、凭据读取或破坏性脚本。
- 版本漂移：FastAPI 和 Vue 规范必须以项目锁定版本及现有结构为边界。
- 规则层级冲突：`AGENTS.md`、Skill 和详细文档必须职责分明，不重复规定同一流程。
- 验证可执行性：文档中的命令必须与当前 Windows/PowerShell 项目实际命令一致。

---

### Task 1: 安装并审计项目级外部 Skill

**Files:**
- Create: `.agents/skills/security-best-practices/**`
- Create: `.agents/skills/security-threat-model/**`
- Create: `.agents/skills/fastapi/**`
- Create: `.agents/skills/SOURCES.md`

**Interfaces:**
- Consumes: OpenAI `openai/skills` curated 路径；FastAPI `fastapi/fastapi` 官方仓库路径。
- Produces: 三个可发现的项目级 Skill，以及记录来源、分支/提交、获取日期和审计结论的来源清单。

- [ ] **Step 1: 确认目标目录和同名冲突**

检查 `.agents/skills/` 尚不存在同名目录，并记录当前全局可用 Skill 中哪些不需要复制。

- [ ] **Step 2: 使用 skill-installer 下载 OpenAI curated Skill**

将 `skills/.curated/security-best-practices` 和 `skills/.curated/security-threat-model` 下载到项目 `.agents/skills/`。

- [ ] **Step 3: 使用 skill-installer 下载 FastAPI 官方 Skill**

将 `fastapi/.agents/skills/fastapi` 下载到项目 `.agents/skills/fastapi`。

- [ ] **Step 4: 审计下载结果**

列出全部文件，完整阅读三个 `SKILL.md`；搜索联网命令、凭据变量、递归删除、任意脚本执行和绝对路径。若发现未说明的高风险行为，停止并报告，不继续启用。

- [ ] **Step 5: 验证 Skill 结构**

对三个目录运行 `skill-creator/scripts/quick_validate.py`。期望：三个 Skill 均通过；若第三方元数据与当前验证器不兼容，记录具体字段，不静默改写上游文件。

- [ ] **Step 6: 写入来源清单**

`SOURCES.md` 记录来源 URL、获取日期、目标目录、许可信息、审计结论和更新策略。

### Task 2: 创建并验证轻量 Vue 工程 Skill

**Files:**
- Create: `.agents/skills/nev-mcdm-vue/SKILL.md`
- Create: `.agents/skills/nev-mcdm-vue/agents/openai.yaml`
- Create: `.agents/skills/nev-mcdm-vue/references/project-conventions.md`
- Create: `.agents/skills/nev-mcdm-vue/tests/scenarios.md`

**Interfaces:**
- Consumes: 当前 Vue 3.5.22、TypeScript 5.9.3、Vite 7.1.9 结构和已有前端拆分经验。
- Produces: 只在修改 `.vue`、前端 composable、ECharts 配置或前端状态所有权时触发的项目专用 Skill。

- [ ] **Step 1: 记录 RED 基线**

在 `tests/scenarios.md` 记录无专用 Skill 时已经观察到的失败：`App.vue` 曾同时承载导航、请求、状态、六个页面和图表配置并增长到约 1476 行；同时定义三个应用场景和两个不应触发的反例。

- [ ] **Step 2: 初始化 Skill**

使用 `skill-creator/scripts/init_skill.py` 创建 `nev-mcdm-vue`，只请求 `references` 资源，不生成无用示例。

- [ ] **Step 3: 写最小 `SKILL.md`**

描述只包含触发条件；正文路由到项目约定，强调根组件装配、状态所有权、组件边界、显式类型和按需加载，不复制通用 Vue 教程。

- [ ] **Step 4: 写项目约定参考**

`project-conventions.md` 固定当前目录边界、共享状态规则、API 调用位置、图表生命周期、可访问性和验证命令。

- [ ] **Step 5: 验证应用场景**

逐项检查 Skill 对“大型页面新增模块”“跨页面状态”“新增图表”能路由到正确约定，并对“后端纯 Python 修改”“仅改 README”不产生触发。因当前任务未授权多代理，不使用子代理；将此限制和人工验证证据写入场景记录。

- [ ] **Step 6: 运行结构验证**

运行 `quick_validate.py .agents/skills/nev-mcdm-vue`。期望：通过，无占位文本；`SKILL.md` 保持精简。

### Task 3: 建立常驻工程约束和规范文档

**Files:**
- Create: `AGENTS.md`
- Create: `docs/开发与架构规范.md`
- Create: `docs/测试与质量门禁.md`
- Create: `docs/文档同步规范.md`
- Create: `docs/Skill使用清单.md`
- Create: `docs/ADR/README.md`
- Create: `docs/ADR/0000-模板.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1 的 Skill 来源与 Task 2 的 Vue 约定。
- Produces: 后续 Codex 和人工开发共同遵循的规则入口、详细规范、质量门禁和架构决策模板。

- [ ] **Step 1: 编写 `AGENTS.md`**

只保留常驻规则：项目边界、目录职责、数据真实性、不可伪造研究结果、变更分级、文档路由、允许直接执行的本机验证命令，以及禁止把本机无鉴权服务暴露公网。

- [ ] **Step 2: 编写开发与架构规范**

定义前后端模块边界、依赖方向、文件拆分判断、API/领域模型/存储/归档职责、命名、错误处理、版本兼容、依赖引入和数据来源规则。

- [ ] **Step 3: 编写测试与质量门禁**

定义后端 pytest、前端类型/格式/构建、浏览器回归、安全输入测试和完成证据；明确不同变更类型需执行的最小验证集合。

- [ ] **Step 4: 编写文档同步规范**

建立“代码变化 → 必须检查的文档”映射，规定 API、数据口径、启动方式、依赖、研究限制和截图发生变化时的更新责任。

- [ ] **Step 5: 编写 Skill 使用清单**

区分全局已有、项目下载、项目自建和条件触发 Skill；记录触发条件、禁用场景、来源和组合顺序。

- [ ] **Step 6: 编写 ADR 模板**

定义编号、状态、背景、决策、备选方案、后果、验证和关联文件；不为已经没有争议的小改动补造 ADR。

- [ ] **Step 7: 更新 README 文档入口**

在 README 增加工程治理入口，不复制各规范正文。

### Task 4: 一致性与最终验证

**Files:**
- Modify: `docs/Skill使用清单.md`（仅在验证结果需要补充时）
- Modify: `.agents/skills/SOURCES.md`（仅在审计结果需要补充时）

**Interfaces:**
- Consumes: Tasks 1–3 的全部产物。
- Produces: 可复核的最终验证结果。

- [ ] **Step 1: 检查 Markdown 链接和占位符**

使用 `rg` 检查 `TODO`、`TBD`、空链接和不存在的相对路径；人工核对 README、AGENTS 和规范文档之间的导航。

- [ ] **Step 2: 验证全部 Skill**

对 `.agents/skills/*/SKILL.md` 所在目录运行 `quick_validate.py`，记录第三方兼容例外。

- [ ] **Step 3: 验证命令真实性**

运行后端测试、前端 `format:check`、`typecheck` 和生产构建；本次只改文档和 Skill，但文档宣称的命令必须真实可用。

- [ ] **Step 4: 审查常驻上下文体积**

确认 `AGENTS.md` 保持精简，详细说明均通过条件式链接路由；确认没有把完整第三方 Skill 内容复制进文档。

- [ ] **Step 5: 汇报结果**

列出新增文件、下载来源、启用条件、验证结果、已知限制，以及下一步如何让用户调整规则。
