# 评论数据工作台与可追溯资产管理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有评论采集模块升级为“获取数据—管理数据—用于研究”的引导式工作台，并为已采集和人工导入评论提供不可篡改原文、可维护元数据、永久删除审计及稳定的多准则研究交接能力。

**Architecture:** 继续以 SQLite 的 `reviews` 表保存唯一原始评论，在其上增加稳定资产标识、独立管理元数据和无原文删除墓碑；采集仓储只负责来源写入，新增资产仓储与服务负责查询、导入、元数据和删除。前端保留任务轮询与目录发现状态，新增独立资产工作区，并将原有四个技术页面收敛为获取、管理、研究三个任务页面。

**Tech Stack:** Python 3.9、FastAPI、Pydantic、SQLite、pytest；Vue 3 Composition API、TypeScript、Vitest、Vite；原生 HTML/CSS，无新增运行时依赖。

**Spec:** `docs/superpowers/specs/2026-10-14-review-asset-workbench-design.md`

## Global Constraints

- `original_review`、`content_hash` 和来源身份只能由采集或导入边界创建，管理 API 不提供原文更新路径。
- 删除真实移除原始 JSON，只保留不含原文、URL、标签和备注的最小审计；不提供恢复或批量永久删除。
- 已创建的研究快照和结果不受源评论删除影响，新任务只读取仍存在且 `analysis_enabled=true` 的资产。
- 人工导入必须标记为 `platform=manual`、`source_kind=manual_import`；汽车之家记录使用 `source_kind=autohome`。
- 导入仅接受 UTF-8 JSON/JSONL 对应的 JSON 数组，最大 8 MB、最多 10,000 条，确认写入必须携带未过期的校验指纹并保持原子性。
- 删除必须校验原因、当前评论 ID、内容哈希和活动采集任务；墓碑默认阻止静默重采。
- 前端只通过 `api.ts` 访问后端；列表与详情请求均使用请求代际隔离，过期响应不得覆盖当前界面。
- 继续使用宋体、白底表格和克制青色提示；不增加渐变、大面积装饰卡片或自动创建研究任务。
- 保留现有 `/reviews` 和导出接口的迁移期兼容性，不改变汽车之家访问频率和验证策略。

## Review Focus

- 旧数据库重复启动或迁移中途失败：必须保持原始 JSON/哈希不变，迁移可重复并在失败时整体回滚；由 Task 2 的迁移测试固定。
- 校验后数据库重复状态发生变化：确认导入必须返回 `409` 且一条也不写入；由 Task 4 的指纹竞争测试固定。
- 删除与采集任务并发：排队、发现、采集或暂停任务涉及同一车系时必须返回 `409`，审计和原文均不发生部分变化；由 Task 5 的事务测试固定。
- 同一车系同时有汽车之家和人工来源、且部分资产禁用或删除：来源数量和新分析快照必须按 `series_id` 聚合并只使用当前启用资产；由 Task 6 的混合来源测试固定。
- 用户快速切换筛选、翻页或关闭抽屉：较慢的旧响应和 `404/410` 不得重新打开详情或覆盖新列表；由 Task 7 的请求代际测试固定。

---

### Task 1: 固化现有已验证修复并建立功能基线

**Files:**
- Verify/commit existing changes: `backend/collection/domain.py`, `backend/collection/repository.py`, `backend/review_analysis/discovery.py`, `backend/review_analysis/service.py`
- Verify/commit existing tests: `backend/tests/test_collection_domain.py`, `backend/tests/test_collection_repository.py`, `backend/tests/test_review_analysis_discovery.py`, `backend/tests/test_review_analysis_service.py`
- Verify/commit existing docs: `docs/API与数据契约.md`, `docs/开发与架构规范.md`

**Interfaces:**
- Consumes: 当前工作树中已经完成但尚未提交的爬取语义哈希和准则发现容错修复。
- Produces: 一个独立、可回退的基线提交；后续任务不把旧修复混入资产工作台提交。

- [ ] **Step 1: 审阅待提交差异**

运行 `git diff --check` 和 `git diff --stat`；确认只包含上述十个文件且没有密钥、数据库或运行产物。

- [ ] **Step 2: 运行现有修复的定向测试**

运行 `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_collection_domain.py backend/tests/test_collection_repository.py backend/tests/test_review_analysis_discovery.py backend/tests/test_review_analysis_service.py -q --basetemp .pytest-tmp`；预期全部通过。

- [ ] **Step 3: 运行后端基线回归**

运行 `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests -q --basetemp .pytest-tmp`；预期全部通过。

- [ ] **Step 4: 提交基线修复**

运行 `git add` 精确暂存上述文件，并提交 `fix: stabilize collection hashes and criteria discovery`。

### Task 2: 建立幂等资产数据库迁移和采集写入契约

**Files:**
- Create: `backend/collection/asset_migrations.py`
- Modify: `backend/collection/repository.py`
- Modify: `backend/review_analysis/repository.py`
- Test: `backend/tests/test_review_asset_migrations.py`
- Test: `backend/tests/test_collection_repository.py`

**Interfaces:**
- Consumes: 现有 `reviews(platform, review_id, ...)` 和 `review_analysis_job_reviews` 表。
- Produces: `ensure_review_asset_schema(connection: sqlite3.Connection) -> None`；`reviews.asset_id`、`reviews.source_kind`；`review_asset_metadata`、可记录多次删除周期的 `review_deletion_audits`；`review_analysis_job_reviews.source_asset_id`；`collection_jobs.deleted_review_skip_count`；采集保存结果增加 `deleted_skipped: int`。

- [ ] **Step 1: 写迁移失败测试**

新增 `test_migration_backfills_legacy_reviews_without_changing_raw_content`、`test_migration_is_idempotent`、`test_migration_rolls_back_as_one_transaction`，断言旧记录得到 `autohome:{review_id}`、默认元数据和分析引用回填，同时迁移前后的 `original_review_json` 与 `content_hash` 完全相同。

- [ ] **Step 2: 运行迁移测试并确认失败**

运行 `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_review_asset_migrations.py -q --basetemp .pytest-tmp`；预期因迁移模块不存在而失败。

- [ ] **Step 3: 实现单一迁移入口**

在 `asset_migrations.py` 实现 `ensure_review_asset_schema(connection)`；使用显式事务、列存在性检查和唯一索引完成幂等回填。删除审计使用独立审计主键并按 `asset_id, deleted_at` 索引，使解除重采后的再次删除仍可保留新一轮审计。人工缺省 URL 在数据库中保存为空字符串，资产 API 再规范化为 `null`，避免破坏旧表的 `NOT NULL` 约束。

- [ ] **Step 4: 接入仓储初始化并固定采集资产标识**

让 `CollectionRepository` 和 `ReviewAnalysisRepository` 初始化时调用迁移；修改 `save_review_page(...) -> dict[str, int]`，新汽车之家评论写入确定性 `asset_id/source_kind` 和默认元数据，命中最新且未解除的墓碑时不写入，同时增加返回值 `deleted_skipped` 和任务累计字段 `deleted_review_skip_count`。

- [ ] **Step 5: 运行迁移与采集仓储测试**

运行 `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_review_asset_migrations.py backend/tests/test_collection_repository.py -q --basetemp .pytest-tmp`；预期全部通过。

- [ ] **Step 6: 提交迁移**

提交 `feat(collection): add review asset schema migration`。

### Task 3: 实现资产查询、管理元数据与统计 API

**Files:**
- Create: `backend/collection/asset_domain.py`
- Create: `backend/collection/asset_repository.py`
- Create: `backend/collection/asset_api.py`
- Modify: `backend/app.py`
- Test: `backend/tests/test_review_asset_repository.py`
- Test: `backend/tests/test_review_asset_api.py`

**Interfaces:**
- Consumes: Task 2 的资产列和元数据表。
- Produces: `ReviewAssetRepository.list_assets(...)`、`get_asset(asset_id)`、`update_metadata(asset_id, command)`、`batch_update_metadata(command)`、`summary()`；`create_review_asset_router(repository, service)`；GET 列表/详情/统计与 PATCH 单条/批量元数据接口。

- [ ] **Step 1: 写查询与元数据失败测试**

覆盖关键词、车系、来源、标签、启用状态和分页组合；断言详情返回只读 `original_review`、引用计数和 `revision`；断言 21 个标签、31 字标签、1001 字备注为 `422`，旧 revision 为 `409`，且任何请求模型都没有原文更新字段。

- [ ] **Step 2: 运行定向测试并确认失败**

运行 `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_review_asset_repository.py backend/tests/test_review_asset_api.py -q --basetemp .pytest-tmp`；预期因资产模块和路由不存在而失败。

- [ ] **Step 3: 实现领域模型和专用仓储**

在 `asset_domain.py` 定义 `MetadataPatchBody`、`BatchMetadataPatchBody`、筛选和响应模型及 `AssetNotFound/AssetConflict/AssetGone`；在 `asset_repository.py` 实现参数化查询、标签规范化、乐观锁 revision、批量启用/禁用和增删标签，禁止批量删除。

- [ ] **Step 4: 实现并装配 API**

在 `asset_api.py` 提供 `/api/collection/review-assets` 下的列表、详情、summary、单条 metadata 和批量 metadata 路由，将领域错误稳定映射为 `404/409/410/422`；在 `app.py` 只创建一次仓储并挂载路由。

- [ ] **Step 5: 运行资产 API 测试**

运行 `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_review_asset_repository.py backend/tests/test_review_asset_api.py -q --basetemp .pytest-tmp`；预期全部通过。

- [ ] **Step 6: 提交查询与元数据功能**

提交 `feat(collection): add review asset management api`。

### Task 4: 实现可预检、可确认的原子人工导入

**Files:**
- Create: `backend/collection/asset_service.py`
- Modify: `backend/collection/asset_domain.py`
- Modify: `backend/collection/asset_repository.py`
- Modify: `backend/collection/asset_api.py`
- Test: `backend/tests/test_review_asset_import.py`
- Test: `backend/tests/test_review_asset_api.py`

**Interfaces:**
- Consumes: Task 3 的资产仓储和领域错误。
- Produces: `ReviewAssetService.validate_import(items, payload_bytes) -> ImportValidationResult`、`import_validated(items, payload_bytes, validation_fingerprint) -> ImportResult`；POST `/review-assets/import/validate` 与 `/review-assets/import`。

- [ ] **Step 1: 写导入契约失败测试**

覆盖单项和多项、行号、空正文、非对象、非法 HTTPS URL、字段超限、非有限数值、8 MB/10,000 条边界、来源 ID 重复和稳定内容哈希重复；断言人工资产 ID 为 `manual:{uuid}`、来源标记正确、原始对象逐字段保留。

- [ ] **Step 2: 写指纹和事务失败测试**

新增 `test_import_rejects_stale_fingerprint_without_partial_write`，在预检后插入竞争重复项，再确认导入；断言返回冲突且其余原本可导入项也没有写入。另用仓储故障注入断言批量中途失败整体回滚。

- [ ] **Step 3: 运行导入测试并确认失败**

运行 `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_review_asset_import.py backend/tests/test_review_asset_api.py -q --basetemp .pytest-tmp`；预期缺少服务和路由而失败。

- [ ] **Step 4: 实现确定性校验与指纹**

由 `asset_service.py` 复用 `backend/review_analysis/text.py` 的文本提取规则，输出 `importable/duplicates/errors/validation_fingerprint`；指纹覆盖规范化输入和当前重复状态，日志与错误不包含正文。

- [ ] **Step 5: 实现单事务确认导入**

在仓储中一次事务写入 `vehicle_series`、`reviews` 和默认元数据；重新校验指纹，不允许部分成功；人工 `review_id` 缺省时生成 UUID，`asset_id` 始终使用独立 UUID。

- [ ] **Step 6: 运行导入与 API 测试**

运行 `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_review_asset_import.py backend/tests/test_review_asset_api.py -q --basetemp .pytest-tmp`；预期全部通过。

- [ ] **Step 7: 提交人工导入**

提交 `feat(collection): add validated manual review import`。

### Task 5: 实现永久删除、删除审计和重采控制

**Files:**
- Modify: `backend/collection/asset_domain.py`
- Modify: `backend/collection/asset_repository.py`
- Modify: `backend/collection/asset_service.py`
- Modify: `backend/collection/asset_api.py`
- Modify: `backend/collection/repository.py`
- Test: `backend/tests/test_review_asset_deletion.py`
- Test: `backend/tests/test_collection_repository.py`

**Interfaces:**
- Consumes: Task 2 的墓碑表、Task 3 的错误映射、Task 4 的资产服务。
- Produces: `delete_asset(asset_id, expected_content_hash, confirmed_review_id, reason)`、`list_deletions(...)`、`allow_recollection(asset_id)`；DELETE 资产、GET 删除记录、POST 允许重采接口。

- [ ] **Step 1: 写删除事务失败测试**

覆盖确认 ID、1～500 字原因、内容哈希冲突、重复删除 `410`；新增 `test_active_job_blocks_delete_without_partial_audit`，逐个验证 `queued/discovering/collecting/paused` 且涉及同一车系时原文、元数据和审计均保持不变。

- [ ] **Step 2: 写研究保留和墓碑失败测试**

先建立分析快照再删除源资产，断言快照/候选/标注仍存在；再次采集同平台同评论 ID 时断言跳过，解除重采后允许重新写入；审计序列化结果不得出现原文、URL、标签或备注。

- [ ] **Step 3: 运行删除测试并确认失败**

运行 `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_review_asset_deletion.py backend/tests/test_collection_repository.py -q --basetemp .pytest-tmp`；预期缺少删除接口而失败。

- [ ] **Step 4: 实现单事务删除与墓碑管理**

使用 `BEGIN IMMEDIATE` 依次读取资产、检查同车系活动任务、核对哈希、写最小审计、删元数据和原文；任何异常整体回滚。解除重采仅写 `recollection_allowed_at`，不重建旧资产。

- [ ] **Step 5: 实现删除 API 和采集跳过事件**

API 要求显式 `confirm=true`、当前评论 ID 和原因；采集仓储将墓碑跳过计入任务统计并记录不含正文的事件。

- [ ] **Step 6: 运行删除、采集和 API 测试**

运行 `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_review_asset_deletion.py backend/tests/test_collection_repository.py backend/tests/test_review_asset_api.py -q --basetemp .pytest-tmp`；预期全部通过。

- [ ] **Step 7: 提交删除治理**

提交 `feat(collection): add permanent deletion audit controls`。

### Task 6: 将有效资产契约接入多准则研究快照

**Files:**
- Modify: `backend/review_analysis/domain.py`
- Modify: `backend/review_analysis/repository.py`
- Modify: `backend/review_analysis/api.py`
- Test: `backend/tests/test_review_analysis_repository.py`
- Test: `backend/tests/test_review_analysis_api.py`
- Test: `backend/tests/test_review_asset_deletion.py`

**Interfaces:**
- Consumes: Task 2 的 `source_asset_id`、Task 3 的 `analysis_enabled`、Task 5 的源删除状态。
- Produces: 按 `series_id` 聚合的 `list_sources(...)`；新快照持久化 `source_asset_id`；详情和标注响应中的 `source_deleted: bool`。

- [ ] **Step 1: 写混合来源和启用范围失败测试**

新增 `test_sources_aggregate_providers_and_snapshots_use_enabled_assets_only`：同一 `series_id` 放入汽车之家与人工资产，禁用一条并删除一条，断言来源只出现一行、数量只含当前启用资产，新任务快照只包含该集合。

- [ ] **Step 2: 写删除后研究可追溯失败测试**

断言删除前快照仍能返回原分析文本和结果，但 `source_deleted=true`；源仍存在时为 `false`；无法回填的历史行保持 `source_asset_id=null` 且不误判其他来源。

- [ ] **Step 3: 运行分析仓储/API 测试并确认失败**

运行 `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_review_analysis_repository.py backend/tests/test_review_analysis_api.py backend/tests/test_review_asset_deletion.py -q --basetemp .pytest-tmp`；预期现有硬编码 `platform='autohome'` 导致失败。

- [ ] **Step 4: 改为有效资产查询和稳定快照引用**

移除按平台拆分的来源逻辑，按 `series_id` 聚合并使用 `reviews JOIN review_asset_metadata` 的启用集合；创建任务和重试任务都复制 `source_asset_id`，查询时通过当前资产存在性计算 `source_deleted`，不建立级联外键。

- [ ] **Step 5: 运行多准则分析回归**

运行 `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_review_analysis_repository.py backend/tests/test_review_analysis_api.py backend/tests/test_review_analysis_service.py backend/tests/test_review_analysis_discovery.py backend/tests/test_review_analysis_annotation.py -q --basetemp .pytest-tmp`；预期全部通过。

- [ ] **Step 6: 提交研究交接契约**

提交 `feat(analysis): consume enabled review assets`。

### Task 7: 建立前端资产 API 类型与独立状态工作区

**Files:**
- Modify: `frontend/src/modules/collection/api.ts`
- Create: `frontend/src/modules/collection/assetWorkspace.ts`
- Create: `frontend/src/modules/collection/assetWorkspace.spec.ts`
- Modify: `frontend/src/modules/collection/workspace.ts`
- Modify: `frontend/src/modules/collection/workspace.spec.ts`

**Interfaces:**
- Consumes: Tasks 3～6 的 HTTP 契约；现有 `CollectionApi` 注入测试模式。
- Produces: `ReviewAssetApi` 请求/响应类型；`createAssetWorkspace(client, registerLifecycle)`；筛选、分页、详情、revision 保存、批量元数据、导入三步状态、删除与 summary 动作；`CollectionPage = "acquire" | "assets" | "research"`。

- [ ] **Step 1: 写资产状态失败测试**

覆盖筛选重置页码、分页、详情开关、元数据成功和 `409` 重载、批量操作、导入预检/确认、删除成功清空详情、`404/410/422` 中文错误恢复和 summary 刷新。

- [ ] **Step 2: 写过期响应隔离失败测试**

用可控 Promise 验证旧筛选列表不得覆盖新筛选结果；关闭抽屉后迟到详情和 `410` 都不得重新打开；停用工作区后所有迟到请求不得写状态。

- [ ] **Step 3: 运行前端状态测试并确认失败**

在 `frontend` 运行 `E:\aaaxz\nodejs0324\npm.cmd test -- --run src/modules/collection/assetWorkspace.spec.ts src/modules/collection/workspace.spec.ts`；预期资产工作区不存在或页面类型不匹配。

- [ ] **Step 4: 扩展统一 API 客户端**

在 `api.ts` 声明并实现资产查询、导入、metadata、删除、删除记录和 summary 方法；保留旧 `/reviews` 方法供迁移兼容，组件不得直接 `fetch`。

- [ ] **Step 5: 实现独立资产状态并瘦身主工作区**

`assetWorkspace.ts` 独占资产生命周期和请求代际；`workspace.ts` 只保留导航、采集任务、任务详情和轮询，移除旧车系/评论页面状态，将默认页面改为 `acquire`。

- [ ] **Step 6: 运行前端状态测试**

在 `frontend` 运行 `E:\aaaxz\nodejs0324\npm.cmd test -- --run src/modules/collection/assetWorkspace.spec.ts src/modules/collection/workspace.spec.ts src/modules/collection/catalogFlow.spec.ts`；预期全部通过。

- [ ] **Step 7: 提交前端状态层**

提交 `feat(frontend): add review asset workspace state`。

### Task 8: 重构获取数据页并实现资产管理界面

**Files:**
- Create: `frontend/src/modules/collection/views/AcquireView.vue`
- Create: `frontend/src/modules/collection/views/AssetsView.vue`
- Create: `frontend/src/modules/collection/components/ReviewImportDialog.vue`
- Create: `frontend/src/modules/collection/components/ReviewAssetDrawer.vue`
- Create: `frontend/src/modules/collection/components/GuidedStageBar.vue`
- Modify: `frontend/src/modules/collection/CollectionWorkbench.vue`
- Modify: `frontend/src/styles/collection.css`
- Test: `frontend/src/modules/collection/collectionViews.spec.ts`
- Remove after replacement: `frontend/src/modules/collection/views/OverviewView.vue`, `frontend/src/modules/collection/views/JobsView.vue`, `frontend/src/modules/collection/views/SeriesView.vue`, `frontend/src/modules/collection/views/ReviewsView.vue`

**Interfaces:**
- Consumes: `CollectionWorkspace`、`CatalogFlow` 和 Task 7 的 `AssetWorkspace`，均由 `CollectionWorkbench.vue` 创建并 provide 一次。
- Produces: “获取数据”和“管理数据”完整界面；导入向导与资产详情抽屉拥有各自焦点和关闭生命周期。

- [ ] **Step 1: 写三阶段与管理交互失败测试**

断言无目录、有目录无评论、暂停任务、运行任务、已有评论五种状态各自只突出一个建议动作；断言管理表包含来源/标签/分析状态，原始 JSON 无编辑控件，且没有批量删除入口。

- [ ] **Step 2: 写导入、抽屉和可访问性失败测试**

断言导入按选择文件、校验预览、确认写入推进并显示错误行号/重复原因；删除必须填写原因和评论 ID；Escape 关闭、初始焦点、关闭后焦点恢复及控件可访问名称均存在。

- [ ] **Step 3: 运行视图测试并确认失败**

在 `frontend` 运行 `E:\aaaxz\nodejs0324\npm.cmd test -- --run src/modules/collection/collectionViews.spec.ts`；预期新视图和组件不存在。

- [ ] **Step 4: 实现获取数据页和紧凑引导条**

把目录发现、车系筛选/选择、任务配置、当前任务控制、人工删除跳过数和折叠历史集中到 `AcquireView.vue`；复用 `CreateCollectionJobDialog` 的表单逻辑时删除重复入口，而不是复制业务状态。

- [ ] **Step 5: 实现管理页、导入向导和详情抽屉**

`AssetsView.vue` 只组合筛选栏、表格和批量元数据；`ReviewImportDialog.vue` 处理本地 UTF-8 JSON/JSONL 解析和三步状态；`ReviewAssetDrawer.vue` 分为只读原始数据、管理信息、研究引用、删除数据四区。

- [ ] **Step 6: 更新工作台装配和样式**

导航改为获取/管理/研究三项，移除重复总览；桌面使用右侧抽屉，390px 使用全屏抽屉，表格只在自身横向滚动；沿用宋体、白底和现有 token。

- [ ] **Step 7: 运行视图与设计契约测试**

在 `frontend` 运行 `E:\aaaxz\nodejs0324\npm.cmd test -- --run src/modules/collection/collectionViews.spec.ts src/modules/collection/assetWorkspace.spec.ts`，再运行 `E:\aaaxz\nodejs0324\npm.cmd run check:design`；预期全部通过。

- [ ] **Step 8: 提交工作台主要界面**

提交 `feat(frontend): redesign guided collection workbench`。

### Task 9: 完成研究交接页、路由意图和端到端引导

**Files:**
- Create: `frontend/src/modules/collection/views/ResearchHandoffView.vue`
- Modify: `frontend/src/modules/collection/CollectionWorkbench.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/router/index.spec.ts`
- Modify: `frontend/src/modules/mcdm/McdmWorkbench.vue`
- Test: `frontend/src/modules/collection/collectionViews.spec.ts`

**Interfaces:**
- Consumes: Task 7 的资产 summary；现有 `#/mcdm` 路由和多准则评论分析页面。
- Produces: 可分析/禁用/来源/车系统计与不可用原因；进入准则发现或评论标注的显式导航意图，不自动创建任务。

- [ ] **Step 1: 写研究交接失败测试**

断言统计使用服务端 summary；两个入口分别携带 `intent=criteria-discovery` 和 `intent=review-annotation`；目标页只定位并提示用户确认来源范围，不创建任务或触发 API。

- [ ] **Step 2: 运行研究交接测试并确认失败**

在 `frontend` 运行 `E:\aaaxz\nodejs0324\npm.cmd test -- --run src/modules/collection/collectionViews.spec.ts src/router/index.spec.ts`；预期研究页或意图处理不存在。

- [ ] **Step 3: 实现研究交接页和路由意图消费**

展示准备度和不可用原因，使用现有路由进入多准则工作台；目标页读取一次意图并切换到相应功能区，保留最终来源选择和“开始”按钮给用户。

- [ ] **Step 4: 运行前端模块回归**

在 `frontend` 运行 `E:\aaaxz\nodejs0324\npm.cmd test -- --run`；预期全部通过。

- [ ] **Step 5: 提交研究交接**

提交 `feat(frontend): guide review assets into mcdm research`。

### Task 10: 更新规范、执行全量验证并完成真实流程验收

**Files:**
- Modify: `docs/API与数据契约.md`
- Modify: `docs/开发与架构规范.md`
- Modify: `README.md`
- Modify if needed: `backend/README.md`
- Create: `backend/tests/fixtures/import/reviews-valid.jsonl`
- Create: `backend/tests/fixtures/import/reviews-invalid.jsonl`

**Interfaces:**
- Consumes: Tasks 2～9 的最终行为。
- Produces: 可供后续开发遵循的接口、不可变性、删除和启动说明；全量验证证据。

- [ ] **Step 1: 更新工程和运行文档**

记录资产表职责、导入/删除 API、原文不可修改、墓碑语义、分析快照保留、三阶段页面和本地启动方式；示例只引用脱敏测试夹具，不写 API key 或真实评论。

- [ ] **Step 2: 运行后端全量测试**

运行 `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests -q --basetemp .pytest-tmp`；预期全部通过。

- [ ] **Step 3: 运行前端全量质量门**

在 `frontend` 依次运行 `E:\aaaxz\nodejs0324\npm.cmd test -- --run`、`npm.cmd run check:design`、`npm.cmd run format:check`、`npm.cmd run typecheck`、`npm.cmd run build`；预期全部通过且构建无错误。

- [ ] **Step 4: 使用临时数据库完成后端真实流程验收**

启动指向临时 SQLite 的服务，使用小型夹具完成“人工预检→确认导入→改元数据→建立分析快照→永久删除→确认快照仍在→解除重采”；不得删除 `.runtime/platform.sqlite3` 中的正式评论。

- [ ] **Step 5: 完成桌面与 390px 浏览器验收**

按“发现或导入→管理→用于研究”走通；检查表格自身滚动、全屏抽屉、Escape、焦点恢复、错误重试与刷新后状态。联网采集冒烟若执行，严格限制最多 3 个车系、每车系最多 2 页。

- [ ] **Step 6: 检查提交边界和敏感信息**

运行 `git diff --check`、`git status --short` 和密钥模式检查；确认数据库、`.env`、日志、构建产物和真实导入文件未进入版本控制。

- [ ] **Step 7: 提交文档和验收夹具**

提交 `docs: document review asset workbench operations`。

