# 大模型准则发现与评论级语义标注 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在多准则决策系统中接入 DeepSeek-V4.1-Flash，实现可审核的准则发现和绑定冻结准则版本的逐评论语义标注。

**Architecture:** 新增独立 `backend/review_analysis/` 模块，把文本转换、Prompt、DeepSeek 传输、持久化、两类分析管线和 HTTP 边界分开；任务创建时保存不可变评论文本快照，并用评论哈希、准则指纹、模型和 Prompt 哈希复用结果。前端在多准则工作台内增加独立评论语义分析子工作区，不导入采集模块状态，只通过项目级分析 API 读取已采集资产。

**Tech Stack:** Python 3.11、FastAPI 0.128.8、Pydantic 2.12.2、SQLite、httpx 0.28.1、Vue 3.5.22、TypeScript 5.9.3、Vitest 5.0.2、PowerShell 5.1/7

**Spec:** `docs/superpowers/specs/2026-10-10-llm-review-analysis-design.md`

## Global Constraints

- DeepSeek-V4.1-Flash 的 API 标识固定默认为 `deepseek-flash`，基础地址默认为 `https://api.deepseek.com`。
- 真实 Key 只从本机环境读取；`.env`、数据库、前端、日志、导出和 Git 均不得包含真实 Key。
- 不增加 OpenAI SDK 或 dotenv 依赖；复用已锁定的 `httpx`，启动脚本安全加载简单 `KEY=VALUE` 环境文件。
- 评论标注只接受冻结的自定义准则版本，模型不得创建体系外准则或等级。
- 原始 `original_review` 保持不变；任务保存派生的完整 `analysis_text` 快照，不拆成多条评论。
- 模型隐藏思维链不保存、不展示；只保存原文证据和长度受限的简短判定依据。
- 本计划不生成训练用月度概率矩阵，不训练 BEAST，不重跑归档预测。
- 自动化测试完全离线，必须使用假 DeepSeek 客户端或 `httpx.MockTransport`。
- 后端继续只监听 `127.0.0.1`；不得扩大现有无鉴权服务的网络边界。
- 实施 FastAPI/Pydantic 代码前读取项目 `$fastapi` Skill，实施 Vue 页面结构前读取项目 `$nev-mcdm-vue` Skill，并以本项目锁定版本和 AGENTS.md 为准。
- 所有行为变更按 RED → GREEN → REFACTOR 执行；每项任务提交前运行其相关测试。

## Review Focus

- **任务创建后原评论被重新采集更新：** Task 3 的 `test_job_uses_snapshotted_analysis_text_after_source_changes` 必须证明继续任务仍使用创建时文本。
- **两条不同评论 ID 具有完全相同正文：** Task 5 的 `test_duplicate_content_reuses_result_but_preserves_both_review_links` 必须证明只调用一次且两条评论都可追溯。
- **候选方案审核期间草稿 revision 已变化：** Task 7 的 `test_apply_proposal_rejects_stale_revision_without_mutating_schema` 必须返回 409 并保留候选方案。
- **认证、余额或配置错误包含敏感信息：** Task 2 与 Task 6 的测试必须证明错误被归类为暂停条件且响应、日志和数据库均不包含 Key。
- **用户切换项目或任务后旧轮询才返回：** Task 8 的 `stale responses cannot replace the active project or job` 必须证明过期响应被丢弃。

---

### Task 1: 建立领域契约、完整评论文本转换和版本化 Prompt

**Files:**
- Create: `backend/review_analysis/__init__.py`
- Create: `backend/review_analysis/domain.py`
- Create: `backend/review_analysis/text.py`
- Create: `backend/review_analysis/prompting.py`
- Create: `backend/review_analysis/prompts/criteria_discovery_v1.txt`
- Create: `backend/review_analysis/prompts/criteria_merge_v1.txt`
- Create: `backend/review_analysis/prompts/review_annotation_v1.txt`
- Create: `backend/tests/test_review_analysis_domain.py`
- Create: `backend/tests/test_review_analysis_prompting.py`

**Interfaces:**
- Produces: `extract_analysis_text(original_review: Mapping[str, Any]) -> str`
- Produces: `schema_fingerprint(criteria: Sequence[CriterionSnapshot]) -> str`
- Produces: `stable_stratified_sample(rows: Sequence[ReviewAsset], limit: int) -> list[ReviewAsset]`
- Produces: `parse_criteria_proposal(payload: Any) -> CriteriaProposal`
- Produces: `parse_review_annotation(payload: Any, *, criteria: Sequence[CriterionSnapshot], review_text: str) -> ReviewAnnotationResult`
- Produces: Pydantic 模型 `CriterionSnapshot`、`ProposalCriterion`、`CriteriaProposal`、`ReviewAnnotationItem`、`ReviewAnnotationResult`、`PromptManifest`、`RenderedPrompt`、`CreateJobCommand`、`ReviewAsset`、`ReviewSnapshot`、`ControlAction`
- Produces: `PromptRenderer.discovery_batch(...)`、`PromptRenderer.criteria_merge(...)`、`PromptRenderer.review_annotation(...)`

- [ ] **Step 1: 编写领域和文本转换失败测试**

覆盖 `feeling_summary` 与 `contents` 原顺序、完全重复文本去重、空评论拒绝、准则顺序影响指纹、稳定分层选样，以及评论标注中的体系外准则、体系外等级、重复准则和非原文证据被拒绝。

同时断言未知字段被拒绝、`basis` 超长被拒绝，避免模型契约漂移被静默接受。

- [ ] **Step 2: 运行测试并确认因模块尚不存在而失败**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_domain.py -q`

Expected: FAIL，原因是 `backend.review_analysis.domain` 或 `text` 尚不存在。

- [ ] **Step 3: 实现最小领域模型、文本转换、指纹和稳定选样**

`schema_fingerprint` 对保持原顺序的 `[{"name": ..., "labels": [...]}]` 规范 JSON 计算 SHA-256；稳定样本按车系分层，并以 `sha256(series_id + review_id + content_hash)` 排序后轮转补足上限。

- [ ] **Step 4: 编写 Prompt 渲染失败测试**

断言三种模板版本分别为 `criteria-discovery-v1`、`criteria-merge-v1`、`review-annotation-v1`，哈希随模板正文变化，标注 Prompt 包含完整评论、冻结准则顺序、JSON 示例和“不允许创建新准则”等约束，但不要求输出 `chain_of_thought`。

- [ ] **Step 5: 运行 Prompt 测试并确认失败**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_prompting.py -q`

Expected: FAIL，原因是模板或 `PromptRenderer` 尚不存在。

- [ ] **Step 6: 参考师姐 Prompt 实现三个版本化模板和渲染器**

保留市场研究角色、逐项覆盖、多准则命中和有序等级语义；把长篇 CoT 字段改为 `basis`，把证据限制为原文子串，并在每个 Prompt 中包含严格 JSON 示例。

- [ ] **Step 7: 运行 Task 1 测试并确认通过**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_domain.py backend/tests/test_review_analysis_prompting.py -q`

Expected: PASS。

- [ ] **Step 8: 提交 Task 1**

```powershell
git add backend/review_analysis backend/tests/test_review_analysis_domain.py backend/tests/test_review_analysis_prompting.py
git commit -m "feat(criteria): define review analysis contracts"
```

### Task 2: 实现安全环境配置和 DeepSeek JSON 客户端

**Files:**
- Create: `.env.example`
- Create: `scripts/import-local-env.ps1`
- Create: `backend/review_analysis/config.py`
- Create: `backend/review_analysis/deepseek.py`
- Create: `backend/tests/test_review_analysis_deepseek.py`
- Modify: `scripts/start-local.ps1`
- Modify: `backend/tests/test_launch_scripts.py`

**Interfaces:**
- Consumes: Task 1 `RenderedPrompt`
- Produces: `DeepSeekSettings.from_environ(environ: Mapping[str, str]) -> DeepSeekSettings`
- Produces: `DeepSeekClient.complete_json(prompt: RenderedPrompt, *, max_tokens: int) -> JsonCompletion`
- Produces: `LlmConfigurationError`、`LlmAuthenticationError`、`LlmTransientError`、`LlmInvalidResponseError`
- Produces: PowerShell `Import-LocalEnv -Path <path>`

- [ ] **Step 1: 编写 DeepSeek 客户端失败测试**

用 `httpx.MockTransport` 断言请求发送到 `/chat/completions`，使用 `deepseek-flash`、`response_format=json_object` 和关闭 thinking；解析 token 用量；空 `content`、`finish_reason=length`、非法 JSON、401/403、429/5xx 分别映射到正确异常；所有公开异常文本不包含假 Key。

- [ ] **Step 2: 运行客户端测试并确认失败**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_deepseek.py -q`

Expected: FAIL，原因是配置和客户端尚不存在。

- [ ] **Step 3: 实现设置读取和最小 DeepSeek 客户端**

只读取 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL` 和 `DEEPSEEK_REQUEST_TIMEOUT_SECONDS`；日志和异常不得包含 Authorization 头或响应请求体。

- [ ] **Step 4: 编写环境文件加载失败测试**

在临时目录创建含注释、空值、等号和值中类似 PowerShell 表达式的 `.env`，调用 `Import-LocalEnv` 后断言值按字面量设置、已有进程环境不被覆盖、表达式没有执行；同时把新脚本加入 PowerShell 语法解析清单。

- [ ] **Step 5: 运行启动脚本测试并确认失败**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_launch_scripts.py -q`

Expected: FAIL，原因是 `import-local-env.ps1` 尚不存在或启动脚本未调用它。

- [ ] **Step 6: 添加 `.env.example`、安全加载函数并接入 `start-local.ps1`**

解析器只接受 `^[A-Za-z_][A-Za-z0-9_]*=`，按第一个等号拆分，不调用 `Invoke-Expression`，不把值打印到控制台。`.env.example` 保持空 Key，`.env` 继续被现有忽略规则排除。

- [ ] **Step 7: 运行 Task 2 测试并确认通过**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_deepseek.py backend/tests/test_launch_scripts.py -q`

Expected: PASS。

- [ ] **Step 8: 提交 Task 2**

```powershell
git add .env.example scripts/import-local-env.ps1 scripts/start-local.ps1 backend/review_analysis/config.py backend/review_analysis/deepseek.py backend/tests/test_review_analysis_deepseek.py backend/tests/test_launch_scripts.py
git commit -m "feat(criteria): add DeepSeek environment client"
```

### Task 3: 建立分析任务、不可变文本快照、候选方案和结果缓存仓储

**Files:**
- Create: `backend/review_analysis/repository.py`
- Create: `backend/tests/test_review_analysis_repository.py`

**Interfaces:**
- Consumes: Task 1 `extract_analysis_text`、`stable_stratified_sample` 和领域模型
- Produces: `ReviewAnalysisRepository(path: Path)`
- Produces: `list_sources(query: str, page: int, page_size: int) -> dict[str, Any]`
- Produces: `create_job_with_snapshot(command: CreateJobCommand, build_snapshot: Callable[[list[ReviewAsset]], list[ReviewSnapshot]]) -> dict[str, Any]`
- Produces: `get_job`、`list_jobs`、`active_job`、`request_control`、`pause_interrupted_jobs`
- Produces: `pending_review_snapshots`、`mark_review_succeeded`、`mark_review_failed`
- Produces: `save_proposal`、`get_proposal`、`apply_proposal`
- Produces: `find_cached_result`、`save_result`

- [ ] **Step 1: 编写迁移、来源列表和原子任务创建失败测试**

覆盖新数据库建表、旧数据库非破坏升级、车系评论数、无评论/重复车系拒绝、任务与快照同事务、活动任务互斥以及 `analysis_text` 不为空。

- [ ] **Step 2: 运行仓储测试并确认失败**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_repository.py -q`

Expected: FAIL，原因是仓储尚不存在。

- [ ] **Step 3: 实现表结构、来源读取和任务快照事务**

创建 `review_analysis_jobs`、`review_analysis_job_reviews`、`criteria_proposals`、`review_annotation_results`；任务创建事务读取 `reviews.original_review_json`，在事务内调用纯 `build_snapshot`，并保存派生 `analysis_text`。

- [ ] **Step 4: 编写快照、缓存和 revision 冲突失败测试**

增加 `test_job_uses_snapshotted_analysis_text_after_source_changes`、缓存键四要素变化失效、相同正文可复用结果、候选方案仅成功应用一次、旧 revision 不修改 `schemas`。

- [ ] **Step 5: 运行新增测试并确认失败**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_repository.py -q`

Expected: FAIL，原因是结果和候选方案方法尚未实现。

- [ ] **Step 6: 实现检查点、结果缓存和候选方案乐观锁**

`review_annotation_results` 不绑定评论 ID；任务评论通过 `annotation_id` 关联结果。`apply_proposal` 在同一事务中检查项目、草稿状态和 revision，成功后记录 `applied_schema_id/applied_revision`。

- [ ] **Step 7: 运行 Task 3 测试并确认通过**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_repository.py -q`

Expected: PASS。

- [ ] **Step 8: 提交 Task 3**

```powershell
git add backend/review_analysis/repository.py backend/tests/test_review_analysis_repository.py
git commit -m "feat(criteria): persist review analysis jobs"
```

### Task 4: 实现准则发现的分批线索和全局归并管线

**Files:**
- Create: `backend/review_analysis/discovery.py`
- Create: `backend/review_analysis/structured_calls.py`
- Create: `backend/tests/test_review_analysis_discovery.py`

**Interfaces:**
- Consumes: Tasks 1–3 的 Prompt、客户端异常、仓储任务与快照
- Produces: `StructuredCallExecutor.call(prompt: RenderedPrompt, validator: Callable[[Any], T], *, max_tokens: int, attempts: int) -> tuple[T, JsonCompletion]`
- Produces: `CriteriaDiscoveryPipeline.run(job_id: str, control: Callable[[], ControlAction | None]) -> None`

- [ ] **Step 1: 编写分批、用量累计和成功归并失败测试**

构造多个长评论快照，断言批次不跨评论截断、每批遵守字符预算、全部 clues 进入一次全局归并、合法候选方案被保存且 token 用量累加。

- [ ] **Step 2: 运行发现管线测试并确认失败**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_discovery.py -q`

Expected: FAIL，原因是发现管线尚不存在。

- [ ] **Step 3: 实现结构化调用重试器和发现管线正常路径**

按 40,000 字符且每批最多 100 条评论分组；API 临时错误最多 3 次，业务结构错误最多 2 次；归并成功后用 Task 1 领域模型再次校验并保存。

- [ ] **Step 4: 编写失败与控制路径测试**

覆盖空 content、非法 clues、非法最终准则、全局归并失败、暂停/取消在相邻调用之间生效，以及认证错误立即上抛为暂停条件。

- [ ] **Step 5: 运行新增测试并确认失败**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_discovery.py -q`

Expected: FAIL，原因是失败状态或控制检查尚未实现。

- [ ] **Step 6: 完成错误分类、检查点和协作式控制**

准则全局归并最终失败时不保存半成品 proposal；暂停和取消只在当前请求结束后、下一请求开始前改变状态。

- [ ] **Step 7: 运行 Task 4 测试并确认通过**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_discovery.py -q`

Expected: PASS。

- [ ] **Step 8: 提交 Task 4**

```powershell
git add backend/review_analysis/discovery.py backend/review_analysis/structured_calls.py backend/tests/test_review_analysis_discovery.py
git commit -m "feat(criteria): discover criteria from review samples"
```

### Task 5: 实现逐评论标注、严格证据校验和缓存复用

**Files:**
- Create: `backend/review_analysis/annotation.py`
- Create: `backend/tests/test_review_analysis_annotation.py`

**Interfaces:**
- Consumes: Tasks 1–4 的冻结准则快照、Prompt、结构化调用器、结果缓存和任务评论快照
- Produces: `ReviewAnnotationPipeline.run(job_id: str, control: Callable[[], ControlAction | None]) -> None`

- [ ] **Step 1: 编写多准则命中和合法空结果失败测试**

断言一条评论可保存多个不同准则，每项等级属于冻结体系且证据为原文；`annotations=[]` 在模型明确返回成功 JSON 时是合法成功，不与 API 异常混淆。

- [ ] **Step 2: 运行标注管线测试并确认失败**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_annotation.py -q`

Expected: FAIL，原因是标注管线尚不存在。

- [ ] **Step 3: 实现单评论请求、验证和结果保存正常路径**

每条评论调用前先查四要素缓存；新结果保存到 `review_annotation_results`，再把任务评论关联到结果并递增任务计数。

- [ ] **Step 4: 编写缓存、失败隔离和控制失败测试**

增加 `test_duplicate_content_reuses_result_but_preserves_both_review_links`；覆盖体系外准则、体系外等级、伪造证据连续两次失败后只标记该评论失败，后续评论继续；暂停/取消不重复处理已成功项。

- [ ] **Step 5: 运行新增测试并确认失败**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_annotation.py -q`

Expected: FAIL，原因是缓存或单项失败逻辑尚未完成。

- [ ] **Step 6: 完成缓存复用、逐项错误记录和终态计算**

所有成功为 `completed`，存在逐项失败为 `partial_failed`；异常空内容不得保存为空标注。缓存命中保留当前任务评论自身的 ID、车系和顺序。

- [ ] **Step 7: 运行 Task 5 测试并确认通过**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_annotation.py -q`

Expected: PASS。

- [ ] **Step 8: 提交 Task 5**

```powershell
git add backend/review_analysis/annotation.py backend/tests/test_review_analysis_annotation.py
git commit -m "feat(criteria): annotate reviews against frozen schemas"
```

### Task 6: 实现单工作器任务编排、暂停恢复和失败项重试

**Files:**
- Create: `backend/review_analysis/service.py`
- Create: `backend/tests/test_review_analysis_service.py`

**Interfaces:**
- Consumes: Tasks 2–5 的设置、管线和仓储
- Produces: `ReviewAnalysisService.start(job_id: str) -> Future[None]`
- Produces: `pause(job_id: str) -> None`、`resume(job_id: str) -> Future[None]`、`cancel(job_id: str) -> None`
- Produces: `retry_failures(job_id: str) -> dict[str, Any]`、`shutdown() -> None`

- [ ] **Step 1: 编写正常调度和单活动任务失败测试**

断言服务按 `job_type` 分派到正确管线，同一时刻拒绝第二个活动任务，后台完成后允许下一个任务，查询操作不受互斥影响。

- [ ] **Step 2: 运行服务测试并确认失败**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_service.py -q`

Expected: FAIL，原因是服务尚不存在。

- [ ] **Step 3: 实现线程池、任务分派和基础控制**

使用 `ThreadPoolExecutor(max_workers=1)`；状态变化先持久化再提交；控制请求采用协作式检查，不强杀正在进行的 HTTP 请求。

- [ ] **Step 4: 编写恢复、安全暂停和失败项重试失败测试**

覆盖关闭时暂停、启动时遗留 `queued/running` 转暂停、认证/余额/配置错误暂停且 Key 不入库、重试任务只快照原任务失败项、重复恢复不创建并发执行。

- [ ] **Step 5: 运行新增测试并确认失败**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_service.py -q`

Expected: FAIL，原因是恢复或安全暂停逻辑尚未完成。

- [ ] **Step 6: 完成恢复、错误归类、关闭和失败项新任务**

认证、余额和配置错误保留稳定错误码与不含敏感信息的中文提示；修复环境后从第一个未完成快照继续。

- [ ] **Step 7: 运行 Task 6 测试并确认通过**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_service.py -q`

Expected: PASS。

- [ ] **Step 8: 提交 Task 6**

```powershell
git add backend/review_analysis/service.py backend/tests/test_review_analysis_service.py
git commit -m "feat(criteria): orchestrate resumable LLM jobs"
```

### Task 7: 增加项目级分析 API 并接入应用生命周期

**Files:**
- Create: `backend/review_analysis/api.py`
- Create: `backend/tests/test_review_analysis_api.py`
- Modify: `backend/app.py`
- Modify: `backend/tests/test_platform.py`

**Interfaces:**
- Consumes: Tasks 1–6 的仓储、服务和设置
- Produces: `create_review_analysis_router(repository, service, settings) -> APIRouter`
- Produces: 规格第 10 节的 `/api/projects/{project_id}/review-analysis` 全部端点
- Extends: `create_app(..., review_analysis_service_factory=None)` 和 lifespan shutdown

- [ ] **Step 1: 编写来源、任务创建和状态码失败测试**

覆盖来源分页；无 Key 返回 503 且不创建任务；发现任务仅接受自定义草稿；标注任务仅接受冻结自定义版本；空选择、重复车系、无评论为 422；活动任务冲突为 409。

- [ ] **Step 2: 运行 API 测试并确认失败**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_api.py -q`

Expected: FAIL，原因是路由尚不存在。

- [ ] **Step 3: 实现来源、任务、控制、详情和结果查询端点**

HTTP 层只编排和映射稳定错误码；DeepSeek 请求、Prompt 和 SQL 不进入路由函数。列表使用服务端分页，结果筛选不触发模型调用。

- [ ] **Step 4: 编写候选应用、重试和生命周期失败测试**

增加 `test_apply_proposal_rejects_stale_revision_without_mutating_schema`；覆盖 proposal 读取/应用、失败项重试、summary 计数、应用关闭调用 service shutdown、重启暂停遗留任务。

- [ ] **Step 5: 运行新增测试并确认失败**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_api.py backend/tests/test_platform.py -q`

Expected: FAIL，原因是候选方案或应用装配尚未完成。

- [ ] **Step 6: 完成路由装配、状态映射和应用生命周期**

把 repository/service 放入 `app.state` 供测试诊断；lifespan 先暂停遗留任务，关闭时等待当前调用结束并保存暂停状态。

- [ ] **Step 7: 运行后端相关测试并确认通过**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_review_analysis_*.py backend/tests/test_platform.py backend/tests/test_launch_scripts.py -q`

Expected: PASS。

- [ ] **Step 8: 提交 Task 7**

```powershell
git add backend/review_analysis/api.py backend/app.py backend/tests/test_review_analysis_api.py backend/tests/test_platform.py
git commit -m "feat(criteria): expose review analysis API"
```

### Task 8: 建立前端类型化 API 和评论分析子工作区

**Files:**
- Create: `frontend/src/modules/mcdm/review-analysis/api.ts`
- Create: `frontend/src/modules/mcdm/review-analysis/workspace.ts`
- Create: `frontend/src/modules/mcdm/review-analysis/workspace.spec.ts`
- Modify: `frontend/src/modules/mcdm/McdmWorkbench.vue`

**Interfaces:**
- Consumes: Task 7 HTTP 契约；现有 MCDM 当前项目和 schema refs
- Produces: `ReviewAnalysisApi` 与 `createReviewAnalysisApi(fetcher?)`
- Produces: `createReviewAnalysisWorkspace(api, projectId, schemaId, schemaStatus)`
- Produces: `provideReviewAnalysisWorkspace`、`useReviewAnalysisWorkspace`

- [ ] **Step 1: 编写来源、创建、控制和筛选状态失败测试**

使用假 API 断言项目/版本变化重置来源和结果，创建发现/标注任务传递正确范围，暂停/继续/取消后刷新，筛选只请求列表不创建任务；候选方案的增删、排序、名称和等级编辑只改变本地审核副本，应用时携带当前 revision。

- [ ] **Step 2: 运行 workspace 测试并确认失败**

Run: `Set-Location frontend; & 'E:\aaaxz\nodejs0324\npm.cmd' test -- --run src/modules/mcdm/review-analysis/workspace.spec.ts`

Expected: FAIL，原因是 API/workspace 尚不存在。

- [ ] **Step 3: 实现类型化传输和单一状态源**

复用现有错误解码风格；workspace 管理来源、任务、候选方案、注释分页、筛选、busy/error 和轮询，不包含大段页面模板。

- [ ] **Step 4: 编写轮询竞态和停用失败测试**

增加 `stale responses cannot replace the active project or job`，并断言只有活动任务轮询、页面停用清理 timer、旧项目响应不能覆盖新项目、proposal 编辑内容在 revision 冲突后保留。

- [ ] **Step 5: 运行新增测试并确认失败**

Run: `Set-Location frontend; & 'E:\aaaxz\nodejs0324\npm.cmd' test -- --run src/modules/mcdm/review-analysis/workspace.spec.ts`

Expected: FAIL，原因是竞态保护或生命周期尚未完成。

- [ ] **Step 6: 完成轮询代际保护并由 `McdmWorkbench.vue` 唯一创建子工作区**

不得在页面组件中重复 `createReviewAnalysisWorkspace()`；平台层和采集模块不得导入该 workspace。

- [ ] **Step 7: 运行 Task 8 测试并确认通过**

Run: `Set-Location frontend; & 'E:\aaaxz\nodejs0324\npm.cmd' test -- --run src/modules/mcdm/review-analysis/workspace.spec.ts`

Expected: PASS。

- [ ] **Step 8: 提交 Task 8**

```powershell
git add frontend/src/modules/mcdm/review-analysis frontend/src/modules/mcdm/McdmWorkbench.vue
git commit -m "feat(frontend): add review analysis workspace"
```

### Task 9: 实现评论语义分析页面、候选审核和结果详情

**Files:**
- Create: `frontend/src/modules/mcdm/views/ReviewAnalysisView.vue`
- Create: `frontend/src/modules/mcdm/review-analysis/components/SourceScopePanel.vue`
- Create: `frontend/src/modules/mcdm/review-analysis/components/CriteriaProposalEditor.vue`
- Create: `frontend/src/modules/mcdm/review-analysis/components/AnnotationResults.vue`
- Modify: `frontend/src/modules/mcdm/McdmWorkbench.vue`
- Modify: `frontend/src/modules/mcdm/workspace.ts`
- Modify: `frontend/src/styles/pages.css`
- Modify: `frontend/scripts/check-design-contract.mjs`

**Interfaces:**
- Consumes: Task 8 `useReviewAnalysisWorkspace`
- Produces: MCDM `Page` 值 `review-analysis` 和侧栏入口“评论语义分析”
- Produces: 三段式来源/任务/结果页面和 proposal 编辑事件

- [ ] **Step 1: 先扩展设计契约并确认失败**

要求 Workbench 只创建一次分析 workspace；页面包含“评论语义分析”“准则发现”“逐条评论标注”“原文证据”“待补充线索”；样式包含桌面、1199px 和 767px 三档布局，且页面不导入 collection workspace/API。

Run: `Set-Location frontend; & 'E:\aaaxz\nodejs0324\npm.cmd' run check:design`

Expected: FAIL，原因是页面和样式尚不存在。

- [ ] **Step 2: 实现来源范围和任务控制界面**

草稿只显示准则发现入口，冻结自定义版本只显示逐评论标注入口；创建前显示评论数、预计调用数、传输提示；“全部”需要二次确认。

- [ ] **Step 3: 实现候选方案审核和应用界面**

支持名称、等级、相关词、证据和依据查看，支持增删/排序/编辑名称与等级；应用成功后进入现有准则页，冲突时保留本地编辑。

- [ ] **Step 4: 实现注释列表、筛选和详情界面**

列表展示车系、评论 ID、命中数、状态和时间；详情并列显示完整评论、准则等级、证据、依据和未匹配片段；失败项提供重试入口。

- [ ] **Step 5: 完成可访问性和响应式样式**

所有字段有 label，状态区使用 `aria-live`，任务按钮提供禁用原因，表格自身滚动且整页不横向溢出；继续使用宋体和现有色彩变量，不添加渐变或装饰动画。

- [ ] **Step 6: 运行前端相关验证并修正格式/类型问题**

Run: `Set-Location frontend; & 'E:\aaaxz\nodejs0324\npm.cmd' test -- --run src/modules/mcdm/review-analysis/workspace.spec.ts`

Run: `Set-Location frontend; & 'E:\aaaxz\nodejs0324\npm.cmd' run check:design`

Run: `Set-Location frontend; & 'E:\aaaxz\nodejs0324\npm.cmd' run typecheck`

Expected: 全部 PASS。

- [ ] **Step 7: 提交 Task 9**

```powershell
git add frontend/src/modules/mcdm frontend/src/styles/pages.css frontend/scripts/check-design-contract.mjs
git commit -m "feat(frontend): build review analysis workflow"
```

### Task 10: 同步规范、运行说明和验收证据并执行全量门禁

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/开发与架构规范.md`
- Modify: `docs/API与数据契约.md`
- Modify: `docs/系统设计与实施路线.md`
- Modify: `docs/运行须知.md`
- Modify: `docs/测试与质量门禁.md`
- Create: `docs/大模型评论语义分析验收记录.md`

**Interfaces:**
- Consumes: Tasks 1–9 的实际接口、状态、环境变量和页面行为
- Produces: 当前能力、限制、配置、操作、故障恢复和验证证据的统一文档口径

- [ ] **Step 1: 更新架构、API 和产品路线文档**

写明 `backend/review_analysis/` 边界、任务/快照/缓存表、项目级 API、封闭准则体系、评论级输出和“本阶段不生成训练矩阵”。

- [ ] **Step 2: 更新 `.env` 配置和运行操作说明**

README 与运行须知说明复制 `.env.example` 为 `.env`、填写 `DEEPSEEK_API_KEY`、模型标识、缺 Key 行为、真实文本外部传输、暂停恢复和 Key 轮换；不得写入真实 Key。

- [ ] **Step 3: 更新质量门禁和新增验收记录**

区分假客户端全自动验证与用户填写 Key 后的少量真实 API 冒烟；验收记录只记录模型名、Prompt 版本、数量、终态和 token 用量，不记录完整评论或 Key。

- [ ] **Step 4: 运行完整后端测试**

Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests -q --basetemp .pytest-tmp`

Expected: 全部 PASS，测试输出中没有真实网络请求或 Key。

- [ ] **Step 5: 运行完整前端测试与静态门禁**

Run: `Set-Location frontend; & 'E:\aaaxz\nodejs0324\npm.cmd' test -- --run`

Run: `Set-Location frontend; & 'E:\aaaxz\nodejs0324\npm.cmd' run check:design`

Run: `Set-Location frontend; & 'E:\aaaxz\nodejs0324\npm.cmd' run typecheck`

Run: `Set-Location frontend; & 'E:\aaaxz\nodejs0324\npm.cmd' run format:check`

Run: `Set-Location frontend; & 'E:\aaaxz\nodejs0324\npm.cmd' run build`

Expected: 全部 PASS；只允许记录现有且不影响构建的体积提示。

- [ ] **Step 6: 使用假客户端在真实浏览器验证桌面与窄屏流程**

启动本机站点，验证 `1440×1000` 与 `390×844` 下的来源选择、草稿/冻结限制、发现进度、候选编辑、标注进度、筛选、详情、错误和暂停恢复；控制台无未处理异常，关键 API 无意外 404/500。

- [ ] **Step 7: 验证无 Key 降级和可选真实 API 冒烟边界**

无 Key 时创建 LLM 任务显示明确提示，评论采集、归档浏览和人工准则编辑继续工作。只有用户已填写 Key 时才用少量已保存评论执行真实 API 冒烟；没有 Key 时把该项记录为“未执行：缺少用户凭据”，不得伪造通过结果。

- [ ] **Step 8: 运行 Git 边界检查并提交文档**

Run: `git diff --check`

Run: `git status --short`

确认不包含 `.env`、`.runtime/`、数据库、日志、截图、构建产物或无关变更，然后：

```powershell
git add AGENTS.md README.md docs
git commit -m "docs(criteria): document review analysis workflow"
```

- [ ] **Step 9: 完成功能分支整体验收提交检查**

Run: `git log --oneline --decorate -12`

Run: `git status --short --branch`

Expected: 工作区干净，提交顺序与 Task 1–10 一致；在推送或创建 PR 前使用 `superpowers:requesting-code-review` 和 `superpowers:verification-before-completion`。
