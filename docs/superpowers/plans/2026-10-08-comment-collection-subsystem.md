# 评论数据采集系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在观衡平台新增独立的汽车之家评论数据采集系统，按车系发现和保存完整原始口碑，并提供限速、断点、任务管理、查询和 JSONL 导出。

**Architecture:** FastAPI 挂载独立 `collection` 路由，后台单工作线程通过 Playwright 发现动态车系、通过 HTTPX 分页获取口碑，并由专用 SQLite 仓储原子保存评论与游标。Vue 新增独立 Collection workspace 和四个简化页面；多准则与自适应模块只在未来通过稳定数据标识读取采集资产，不依赖采集适配器。

**Tech Stack:** Python 3.11、FastAPI 0.128.8、Pydantic 2.12.2、SQLite、HTTPX 0.28.1、Playwright 1.63.0、pytest 9.1.1、Vue 3.5.22、TypeScript 5.9.3、Vue Router 4.6.4、Vitest 5.0.2

**Spec:** `docs/superpowers/specs/2026-10-08-comment-collection-subsystem-design.md`

## Global Constraints

- 执行前使用 `superpowers:using-git-worktrees` 建立隔离工作区，不在当前未确认分支上直接堆叠实现。
- 正式数据源固定为 `https://www.autohome.com.cn/price/ev#pvareaid=3311257`，后端不接受任意目标网址。
- 采集单位是唯一 `series_id`；不同年款、改款和配置始终归入同一车系。
- 每条评论必须同时保存 `series_id`、采集时的 `series_name` 和完整 `original_review`；不得拆分、拼接或改写评论。
- 功能验证默认 3 个车系、每车系 2 页；正式模式固定前 500 个唯一车系且每车系页数不设上限。
- 单工作线程；分页请求随机等待 2～4 秒，车系间随机等待 5～10 秒，请求超时 20 秒，重试等待 5、15、45 秒。
- `403`、`429` 或验证页面必须暂停，不得绕过；服务继续只监听 `127.0.0.1`。
- 自动化测试只能使用固定夹具和假客户端，不能访问汽车之家或用户的 `.runtime/platform.sqlite3`。
- 运行数据库、采集结果、JSONL、Cookie、凭据、浏览器会话和 Playwright 产物不得提交 Git。
- 全站字体继续使用 `SimSun, "宋体", STSong, "Songti SC", serif`；Collection 界面保持简洁，不增加卡片墙和装饰性动效。
- 每一任务均按 TDD 执行，提交前运行该任务的相关测试、`git diff --check` 和 `git status --short`。

## Review Focus

- 目录中同一车系出现多个年款或配置链接时，只保存一个车系并保留可用车系名称；Task 3 的 `test_catalog_deduplicates_years_and_requires_name` 固定该行为。
- 分页接口重复返回上一页时，任务必须停止当前车系并记录异常，不能无限请求；Task 4 的 `test_repeated_page_stops_series_without_looping` 固定该行为。
- 进程在一页写入后、下一页请求前退出时，重启必须将活动任务置为可恢复暂停态且不重复数据；Task 2 和 Task 5 的恢复测试共同固定该行为。
- 同一 `review_id` 的原始对象后来发生变化时，应更新当前原始对象并写入变更事件，而不是静默忽略；Task 2 的 `test_review_content_change_is_audited` 固定该行为。
- 原始评论包含大对象、空数组、未知字段或中文嵌套内容时，详情和 JSONL 必须无损返回，列表接口不得携带整份 JSON；Task 5 的 `test_review_detail_and_jsonl_are_lossless` 固定该行为。

---

## File Map

### 后端新增

- `backend/collection/__init__.py`：Collection 包边界。
- `backend/collection/domain.py`：任务配置、状态机、车系/评论值对象、哈希和响应模型。
- `backend/collection/repository.py`：四张 Collection 表、事务、查询、幂等写入和恢复标记。
- `backend/collection/autohome.py`：汽车之家允许列表、Playwright 目录发现和 HTTPX 评论分页适配。
- `backend/collection/service.py`：单工作线程、任务编排、限速、重试、暂停/继续/停止。
- `backend/collection/api.py`：`/api/collection` 路由和 JSONL 流式响应。
- `backend/tests/fixtures/autohome/ev-catalog.html`：最小真实结构脱网夹具。
- `backend/tests/fixtures/autohome/reviews-page-1.json`：包含多个年款/配置的评论分页夹具。
- `backend/tests/fixtures/autohome/reviews-empty.json`：终止页夹具。
- `backend/tests/test_collection_domain.py`：领域约束和状态机。
- `backend/tests/test_collection_repository.py`：持久化、幂等、事务和恢复。
- `backend/tests/test_autohome_adapter.py`：目录和评论响应解析。
- `backend/tests/test_collection_service.py`：任务流程、限速、重试和取消。
- `backend/tests/test_collection_api.py`：HTTP 契约、查询和导出。
- `scripts/install-collection-browser.ps1`：安装与锁定包版本匹配的 Chromium。

### 前端新增

- `frontend/src/modules/collection/api.ts`：Collection HTTP 类型、请求和下载地址。
- `frontend/src/modules/collection/workspace.ts`：模块唯一状态源、轮询和动作。
- `frontend/src/modules/collection/workspace.spec.ts`：轮询、状态更新和错误行为。
- `frontend/src/modules/collection/CollectionWorkbench.vue`：独立壳层和四页装配。
- `frontend/src/modules/collection/views/OverviewView.vue`：简洁数据总览。
- `frontend/src/modules/collection/views/JobsView.vue`：任务创建、进度和控制。
- `frontend/src/modules/collection/views/SeriesView.vue`：车系搜索与分页。
- `frontend/src/modules/collection/views/ReviewsView.vue`：评论列表、详情和 JSONL 导出。
- `frontend/src/styles/collection.css`：Collection 壳层与页面样式。

### 修改

- `backend/requirements.txt`：加入 `playwright==1.63.0`。
- `backend/app.py`：装配 Collection 仓储、服务、生命周期和路由。
- `backend/tests/test_launch_scripts.py`：浏览器安装脚本和启动恢复约束。
- `frontend/src/platform/modules.ts`、`PlatformHome.vue`、`modules.spec.ts`：第三个平级入口。
- `frontend/src/router/index.ts`、`index.spec.ts`、`frontend/src/main.ts`：`/collection` 异步路由。
- `frontend/src/style.css`、`styles/foundation.css`、`styles/platform.css`：样式层和 Collection 识别色。
- `frontend/scripts/check-design-contract.mjs`：模块边界、宋体和简化界面契约。
- `AGENTS.md`、`README.md`、`docs/运行须知.md`、`docs/API与数据契约.md`、`docs/开发与架构规范.md`、`docs/系统设计与实施路线.md`、`docs/测试与质量门禁.md`：同步当前能力和运行边界。
- `docs/ADR/0002-评论采集作为独立平台子系统.md`：记录独立子系统决策。
- `docs/评论数据采集系统验收记录.md`：记录实际命令、联网范围和截图证据。

---

### Task 1: Collection 领域契约与依赖边界

**Files:**
- Create: `backend/collection/__init__.py`
- Create: `backend/collection/domain.py`
- Create: `backend/tests/test_collection_domain.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Consumes: 无；只依赖 Pydantic 和标准库。
- Produces: `JobMode`、`JobStatus`、`CreateJobBody`、`JobConfig`、`VehicleSeries`、`ReviewPage`、`CollectedReview`、`TaskControlError`、`transition_status(current, action)`、`canonical_review_hash(payload)`。

- [ ] **Step 1: 写失败的任务配置与状态机测试**

  在 `test_collection_domain.py` 添加：
  - `test_verification_defaults_to_three_series_and_two_pages`
  - `test_production_is_fixed_to_500_series_and_unlimited_pages`
  - `test_delay_cannot_be_zero_or_reverse`
  - `test_only_paused_job_can_resume`
  - `test_series_requires_id_and_name`

- [ ] **Step 2: 运行领域测试并确认因模块不存在而失败**

  Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_collection_domain.py -q`

  Expected: FAIL，包含 `ModuleNotFoundError: backend.collection`。

- [ ] **Step 3: 实现明确领域接口**

  `CreateJobBody` 只接受 `mode: Literal['verification', 'production']`；验证模式默认 `max_series=3`、`max_pages_per_series=2` 且范围分别为 `1..3`、`1..2`；正式模式强制 `500` 和 `None`。`canonical_review_hash(payload: dict) -> str` 使用 UTF-8、`sort_keys=True`、紧凑分隔符和 SHA-256，但 `CollectedReview.original_review` 保留原始对象。

- [ ] **Step 4: 锁定 Playwright 依赖并运行领域测试**

  在 `backend/requirements.txt` 加入 `playwright==1.63.0`，不升级其他依赖。

  Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_collection_domain.py -q`

  Expected: PASS。

- [ ] **Step 5: 提交领域契约**

  ```powershell
  git add backend/collection/__init__.py backend/collection/domain.py backend/tests/test_collection_domain.py backend/requirements.txt
  git commit -m "feat(collection): define crawl domain contracts"
  ```

### Task 2: SQLite 仓储、幂等写入与恢复

**Files:**
- Create: `backend/collection/repository.py`
- Create: `backend/tests/test_collection_repository.py`

**Interfaces:**
- Consumes: Task 1 的 `JobConfig`、`VehicleSeries`、`CollectedReview`、`JobStatus`。
- Produces: `CollectionRepository(path: Path)`；方法 `create_job`、`get_job`、`list_jobs`、`active_job`、`set_status`、`save_discovery`、`save_review_page`、`record_event`、`list_series`、`list_reviews`、`get_review`、`iter_reviews_for_export`、`overview`、`pause_interrupted_jobs`。

- [ ] **Step 1: 写失败的仓储 schema 与幂等测试**

  添加：
  - `test_repository_creates_four_collection_tables`
  - `test_series_upsert_keeps_one_id_and_updates_current_name`
  - `test_review_page_saves_reviews_and_cursor_in_one_transaction`
  - `test_duplicate_review_updates_last_confirmed_without_new_row`
  - `test_review_content_change_is_audited`
  - `test_interrupted_active_job_becomes_paused_and_resumable`

- [ ] **Step 2: 运行仓储测试并确认失败**

  Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_collection_repository.py -q`

  Expected: FAIL，包含 `No module named 'backend.collection.repository'`。

- [ ] **Step 3: 实现四表 schema 和事务边界**

  `CollectionRepository` 自己管理与现有数据库同路径的 SQLite 连接并启用外键；建立 `collection_jobs`、`vehicle_series`、`reviews`、`collection_events`。`save_review_page(job_id, series, reviews, next_page, saved_at)` 必须在一个事务内完成评论 upsert、内容变化事件、统计和下一页游标更新。

- [ ] **Step 4: 实现分页查询与无损导出迭代器**

  列表方法只返回索引摘要；`get_review(review_id)` 和 `iter_reviews_for_export(series_id)` 解析并返回完整 `original_review`。所有分页固定返回 `rows`、`total`、`page`、`page_size`。

- [ ] **Step 5: 运行仓储测试并提交**

  Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_collection_repository.py -q`

  Expected: PASS。

  ```powershell
  git add backend/collection/repository.py backend/tests/test_collection_repository.py
  git commit -m "feat(collection): persist crawl jobs and reviews"
  ```

### Task 3: 汽车之家目录与评论适配器

**Files:**
- Create: `backend/collection/autohome.py`
- Create: `backend/tests/fixtures/autohome/ev-catalog.html`
- Create: `backend/tests/fixtures/autohome/reviews-page-1.json`
- Create: `backend/tests/fixtures/autohome/reviews-empty.json`
- Create: `backend/tests/test_autohome_adapter.py`
- Create: `scripts/install-collection-browser.ps1`
- Modify: `backend/tests/test_launch_scripts.py`

**Interfaces:**
- Consumes: Task 1 的 `VehicleSeries`、`ReviewPage`、`CollectedReview`。
- Produces: `AUTOHOME_CATALOG_URL`（值固定为规格中的 URL）、`BrowserSession`、`CatalogDiscoveryResult`、`extract_catalog_series(links)`、`parse_review_page(series, payload)`、`AutohomeCatalogAdapter.discover(max_series)`、`AutohomeCatalogAdapter.open_session()`、`AutohomeReviewAdapter(session, client=None)`、`AutohomeReviewAdapter.fetch_page(series, page_index, page_size=20)`。

- [ ] **Step 1: 固化脱网夹具并写失败的解析测试**

  添加：
  - `test_catalog_deduplicates_years_and_requires_name`
  - `test_catalog_keeps_discovery_order_and_stops_at_limit`
  - `test_review_request_uses_series_id_yearid_zero_and_page_size_twenty`
  - `test_review_page_keeps_complete_original_objects`
  - `test_unknown_or_missing_review_shape_fails_explicitly`
  - `test_only_autohome_hosts_are_allowed`

- [ ] **Step 2: 安装锁定后的 Python 依赖**

  Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pip install -r backend/requirements.txt`

  Expected: 成功安装 `playwright==1.63.0`，不下载浏览器二进制。

- [ ] **Step 3: 运行适配器测试并确认失败**

  Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_autohome_adapter.py -q`

  Expected: FAIL，包含缺失适配器接口。

- [ ] **Step 4: 实现纯解析函数和固定域名请求**

  `parse_review_page` 从响应中取得评论列表和总数，每个列表项原样进入 `original_review`；只提取原始口碑 ID 作为索引。`AutohomeReviewAdapter` 使用 HTTPX、20 秒超时以及固定的汽车之家接口主机，参数必须包含 `seriesId`、`pageIndex`、`pageSize=20`、`yearid=0`。

- [ ] **Step 5: 实现 Playwright 车系发现**

  使用同步 Playwright Chromium 打开固定目录页，从车系卡片链接提取 ID 和名称；滚动加载直到达到 `max_series`，或连续 5 次没有新增车系。空名称链接跳过并记录结构错误；返回的 Cookie 和 User-Agent 只存在 `BrowserSession` 内存对象中，不写数据库或日志。`open_session()` 供恢复任务重新建立临时会话，不重复修改已保存的车系发现顺序。

- [ ] **Step 6: 增加显式浏览器安装脚本**

  `install-collection-browser.ps1` 解析与启动脚本相同的 Python 候选路径，执行 `-m playwright install chromium`，失败时给出中文可行动错误。`test_launch_scripts.py` 断言脚本不使用系统范围安装、不写凭据且锁定 Chromium。

- [ ] **Step 7: 运行适配器和脚本测试**

  Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_autohome_adapter.py backend/tests/test_launch_scripts.py -q`

  Expected: PASS，且不启动浏览器、不访问网络。

- [ ] **Step 8: 提交适配器与安装脚本**

  ```powershell
  git add backend/collection/autohome.py backend/tests/fixtures/autohome backend/tests/test_autohome_adapter.py scripts/install-collection-browser.ps1 backend/tests/test_launch_scripts.py
  git commit -m "feat(collection): add autohome source adapters"
  ```

### Task 4: 单工作线程、限速、重试和断点服务

**Files:**
- Create: `backend/collection/service.py`
- Create: `backend/tests/test_collection_service.py`

**Interfaces:**
- Consumes: Task 2 的 `CollectionRepository`；Task 3 的两个适配器及 `BrowserSession`。
- Produces: `CollectionService(repository, catalog_adapter_factory, review_adapter_factory, sleeper, clock, rng)`；方法 `start(job_id)`、`pause(job_id)`、`resume(job_id)`、`stop(job_id)`、`shutdown()`；内部同步入口 `run_job(job_id)` 供线程和测试直接调用。

- [ ] **Step 1: 写失败的任务主流程测试**

  添加：
  - `test_verification_job_stops_at_three_series_and_two_pages`
  - `test_production_job_has_500_series_and_no_page_cap`
  - `test_repeated_page_stops_series_without_looping`
  - `test_page_commit_advances_resume_cursor`
  - `test_pause_and_stop_take_effect_before_next_request`

- [ ] **Step 2: 写失败的限速与错误测试**

  添加：
  - `test_page_and_series_delays_use_configured_ranges`
  - `test_transient_error_retries_after_5_15_45_seconds`
  - `test_403_429_and_verification_pause_immediately`
  - `test_single_series_failure_continues_and_finishes_partial_failed`
  - `test_second_active_job_is_rejected`

- [ ] **Step 3: 运行服务测试并确认失败**

  Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_collection_service.py -q`

  Expected: FAIL，包含缺失 `CollectionService`。

- [ ] **Step 4: 实现可注入时钟的同步任务核心**

  `run_job` 按 `discovering → collecting → terminal` 编排，所有等待通过注入的 `sleeper(seconds)`，随机数通过注入的 `rng.uniform(low, high)`，从而使测试不真实等待。每次发请求前读取持久化控制状态；每页保存后再更新内存游标。恢复已经完成目录发现的任务时调用 `open_session()` 获得新的临时会话，并从持久化车系和页码继续，不重新排列车系。

- [ ] **Step 5: 用单线程执行器封装后台运行**

  使用 `ThreadPoolExecutor(max_workers=1, thread_name_prefix='collection')`。`start`/`resume` 只提交一个 future；`pause`/`stop` 写持久化控制意图；`shutdown` 等待当前请求结束并关闭执行器，不创建 Celery 或 Redis。

- [ ] **Step 6: 运行服务测试并提交**

  Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_collection_service.py -q`

  Expected: PASS，测试总耗时不包含真实退避等待。

  ```powershell
  git add backend/collection/service.py backend/tests/test_collection_service.py
  git commit -m "feat(collection): orchestrate resumable crawl jobs"
  ```

### Task 5: Collection API、应用生命周期与 JSONL

**Files:**
- Create: `backend/collection/api.py`
- Create: `backend/tests/test_collection_api.py`
- Modify: `backend/app.py`

**Interfaces:**
- Consumes: Task 2 仓储和 Task 4 服务。
- Produces: `create_collection_router(repository, service) -> APIRouter`；`create_app(..., collection_service_factory=None)` 的可测试装配点；规格列出的全部 `/api/collection` 路由。

- [ ] **Step 1: 写失败的 API 契约测试**

  覆盖：
  - `test_create_job_applies_verification_defaults`
  - `test_second_active_job_returns_409`
  - `test_pause_resume_stop_validate_current_state`
  - `test_overview_jobs_and_series_are_paginated`
  - `test_review_list_omits_original_payload`
  - `test_review_detail_and_jsonl_are_lossless`
  - `test_export_requires_known_series`
  - `test_restart_pauses_interrupted_job`

- [ ] **Step 2: 运行 API 测试并确认失败**

  Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_collection_api.py -q`

  Expected: FAIL，`/api/collection/*` 返回 404。

- [ ] **Step 3: 实现 APIRouter 和状态码映射**

  API 只编排输入、服务和响应；领域状态冲突映射为 409，未知资源为 404，输入错误由 Pydantic 返回 422。导出使用 `StreamingResponse`，媒体类型为 `application/x-ndjson; charset=utf-8`，一行一条完整自包含记录。

- [ ] **Step 4: 在应用工厂中装配生命周期**

  `create_app` 创建同一路径的 `CollectionRepository`，启动时调用 `pause_interrupted_jobs(now())`，关闭时调用 `service.shutdown()`；将仓储和服务放入 `app.state` 供测试检查。保持现有两个位置参数兼容。

- [ ] **Step 5: 运行 Collection API 和现有后端回归测试**

  Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests/test_collection_api.py backend/tests/test_platform.py -q`

  Expected: PASS。

- [ ] **Step 6: 提交后端 API**

  ```powershell
  git add backend/collection/api.py backend/tests/test_collection_api.py backend/app.py
  git commit -m "feat(collection): expose crawl management API"
  ```

### Task 6: 平台第三入口与模块路由

**Files:**
- Modify: `frontend/src/platform/modules.ts`
- Modify: `frontend/src/platform/modules.spec.ts`
- Modify: `frontend/src/platform/PlatformHome.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/router/index.spec.ts`
- Modify: `frontend/src/main.ts`
- Modify: `frontend/src/styles/foundation.css`
- Modify: `frontend/src/styles/platform.css`

**Interfaces:**
- Consumes: 现有模块注册表和 Router 工厂。
- Produces: `ModuleId` 新增 `collection`；`PlatformRouteComponents.collection`；异步路由 `/#/collection`；平台首项“评论数据采集系统”。

- [ ] **Step 1: 更新测试以要求三个平级入口**

  `modules.spec.ts` 断言顺序为 `collection`、`mcdm`、`adaptive`，Collection 状态为 `available`、路径为 `/collection`。`router/index.spec.ts` 断言 `/collection` 正确解析且与 MCDM 一样使用 `keepAlive`。

- [ ] **Step 2: 运行相关测试并确认失败**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' test -- --run src/platform/modules.spec.ts src/router/index.spec.ts`

  Expected: FAIL，缺少 `collection`。

- [ ] **Step 3: 实现模块注册、路由和三列平台入口**

  首页文案固定为“发现汽车之家车系，采集并保存完整原始口碑”；三个模块保持平级，不增加强制流向箭头。新增 `--collection-accent`，桌面三列、窄屏单列，沿用宋体和现有无渐变视觉纪律。

- [ ] **Step 4: 运行路由与模块测试**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' test -- --run src/platform/modules.spec.ts src/router/index.spec.ts`

  Expected: PASS。

- [ ] **Step 5: 提交平台入口**

  ```powershell
  git add frontend/src/platform frontend/src/router frontend/src/main.ts frontend/src/styles/foundation.css frontend/src/styles/platform.css
  git commit -m "feat(platform): add comment collection system entry"
  ```

### Task 7: Collection 前端传输、状态与工作区壳

**Files:**
- Create: `frontend/src/modules/collection/api.ts`
- Create: `frontend/src/modules/collection/workspace.ts`
- Create: `frontend/src/modules/collection/workspace.spec.ts`
- Create: `frontend/src/modules/collection/CollectionWorkbench.vue`
- Create: `frontend/src/styles/collection.css`
- Modify: `frontend/src/style.css`
- Modify: `frontend/scripts/check-design-contract.mjs`

**Interfaces:**
- Consumes: Task 5 的 `/api/collection` 契约。
- Produces: `collectionApi` 类型化请求；`createCollectionWorkspace()`；`provideCollectionWorkspace()`；页面类型 `overview | jobs | series | reviews`；工作区唯一实例和轮询生命周期。

- [ ] **Step 1: 写失败的 workspace 测试**

  添加：
  - `test_loads_overview_and_jobs_without_project_context`
  - `test_polls_only_while_active_job_is_running`
  - `test_stale_poll_response_cannot_replace_newer_state`
  - `test_pause_resume_stop_refresh_current_job`
  - `test_deactivation_clears_poll_timer`

- [ ] **Step 2: 运行 workspace 测试并确认失败**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' test -- --run src/modules/collection/workspace.spec.ts`

  Expected: FAIL，缺少 Collection workspace。

- [ ] **Step 3: 实现传输类型和唯一 workspace**

  `api.ts` 定义 `CollectionOverview`、`CollectionJob`、`SeriesRow`、`ReviewSummary`、`ReviewDetail`、`Page<T>` 和 `CreateJobInput`。`workspace.ts` 使用请求序号丢弃过期响应；活动任务每 2 秒轮询，`onActivated` 恢复、`onDeactivated`/`onBeforeUnmount` 停止。

- [ ] **Step 4: 实现简洁工作区壳和样式边界**

  `CollectionWorkbench.vue` 只创建一次 workspace，提供“总览、采集任务、车系、原始评论”四项导航和返回平台。`collection.css` 不出现统计卡片网格、渐变或装饰动画；移动端使用现有抽屉行为和焦点恢复。

- [ ] **Step 5: 扩展设计契约**

  `check-design-contract.mjs` 验证 Collection 文件、四项文案、宋体继承、唯一 workspace 所有者、平台层不导入 Collection workspace/API。

- [ ] **Step 6: 运行 workspace 测试**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' test -- --run src/modules/collection/workspace.spec.ts`

  Expected: PASS。

- [ ] **Step 7: 运行设计契约检查**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' run check:design`

  Expected: PASS。

- [ ] **Step 8: 提交工作区壳**

  ```powershell
  git add frontend/src/modules/collection frontend/src/styles/collection.css frontend/src/style.css frontend/scripts/check-design-contract.mjs
  git commit -m "feat(collection-ui): add collection workspace shell"
  ```

### Task 8: 总览与采集任务界面

**Files:**
- Create: `frontend/src/modules/collection/views/OverviewView.vue`
- Create: `frontend/src/modules/collection/views/JobsView.vue`
- Modify: `frontend/src/modules/collection/CollectionWorkbench.vue`
- Modify: `frontend/src/modules/collection/workspace.ts`
- Modify: `frontend/src/modules/collection/workspace.spec.ts`
- Modify: `frontend/src/styles/collection.css`

**Interfaces:**
- Consumes: Task 7 workspace 的总览、任务列表和任务动作。
- Produces: 验证/正式任务创建对话框、活动任务进度、最近任务表、暂停/继续/停止交互。

- [ ] **Step 1: 添加失败的创建与确认逻辑测试**

  测试验证模式提交 `{mode:'verification', max_series:3, max_pages_per_series:2}`；正式模式在第二次确认前不得调用 API，确认文案明确“前 500 个车系、每车系全部评论”。测试停止不删除已采集数量，非法状态错误原样显示。

- [ ] **Step 2: 运行 workspace 测试并确认失败**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' test -- --run src/modules/collection/workspace.spec.ts`

  Expected: FAIL，缺少任务创建和确认动作。

- [ ] **Step 3: 实现总览和任务页**

  页面只保留一行资产摘要、一个活动任务区和普通任务表。活动任务显示车系序号、车系名称与 ID、页码、保存数量、最后更新时间及文字状态。对话框默认选择功能验证；正式模式需要第二次明确确认。

- [ ] **Step 4: 运行任务界面单元测试**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' test -- --run src/modules/collection/workspace.spec.ts`

  Expected: PASS。

- [ ] **Step 5: 运行 TypeScript 类型检查**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' run typecheck`

  Expected: PASS。

- [ ] **Step 6: 运行前端格式检查**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' run format:check`

  Expected: PASS。

- [ ] **Step 7: 提交任务界面**

  ```powershell
  git add frontend/src/modules/collection frontend/src/styles/collection.css
  git commit -m "feat(collection-ui): manage crawl jobs"
  ```

### Task 9: 车系、原始评论与 JSONL 导出界面

**Files:**
- Create: `frontend/src/modules/collection/views/SeriesView.vue`
- Create: `frontend/src/modules/collection/views/ReviewsView.vue`
- Modify: `frontend/src/modules/collection/CollectionWorkbench.vue`
- Modify: `frontend/src/modules/collection/workspace.ts`
- Modify: `frontend/src/modules/collection/workspace.spec.ts`
- Modify: `frontend/src/styles/collection.css`

**Interfaces:**
- Consumes: Task 7 的车系/评论 API 类型和 Task 5 JSONL 路径。
- Produces: 车系名称/ID 搜索、分页、按车系查看评论摘要、完整 JSON 详情和按车系下载。

- [ ] **Step 1: 写失败的查询状态测试**

  添加：
  - 搜索变化将页码重置为 1，250ms 防抖后请求。
  - 选择车系后评论筛选只传 `series_id`，同时在界面显示 `series_name`。
  - 评论列表对象不被当作详情；打开详情单独请求完整 `original_review`。
  - 下载 URL 只由已存在的 `series_id` 构造，不接受任意网址。

- [ ] **Step 2: 运行 workspace 测试并确认失败**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' test -- --run src/modules/collection/workspace.spec.ts`

  Expected: FAIL，缺少车系和评论查询动作。

- [ ] **Step 3: 实现车系和原始评论页**

  `SeriesView` 表格列固定为车系名称、`series_id`、评论数、发现顺序、最近确认时间。`ReviewsView` 列表只显示索引摘要；详情使用可滚动 `<pre>` 展示完整 JSON；导出按钮名称为“导出该车系 JSONL”。空状态说明如何先创建采集任务。

- [ ] **Step 4: 运行前端全部单元测试**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' test -- --run`

  Expected: PASS。

- [ ] **Step 5: 运行前端设计契约**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' run check:design`

  Expected: PASS。

- [ ] **Step 6: 运行前端格式检查**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' run format:check`

  Expected: PASS。

- [ ] **Step 7: 运行 TypeScript 类型检查**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' run typecheck`

  Expected: PASS。

- [ ] **Step 8: 运行生产构建**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' run build`

  Expected: PASS。

- [ ] **Step 9: 提交数据浏览界面**

  ```powershell
  git add frontend/src/modules/collection frontend/src/styles/collection.css
  git commit -m "feat(collection-ui): browse series and raw reviews"
  ```

### Task 10: 文档、ADR、真实冒烟验证与最终门禁

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/运行须知.md`
- Modify: `docs/API与数据契约.md`
- Modify: `docs/开发与架构规范.md`
- Modify: `docs/系统设计与实施路线.md`
- Modify: `docs/测试与质量门禁.md`
- Create: `docs/ADR/0002-评论采集作为独立平台子系统.md`
- Create: `docs/评论数据采集系统验收记录.md`
- Modify: `frontend/scripts/check-design-contract.mjs`

**Interfaces:**
- Consumes: Tasks 1–9 的实际行为和命令。
- Produces: 可复现的新环境安装、运行、授权前提、数据位置、API 和验收证据。

- [ ] **Step 1: 同步架构、API、运行和测试文档**

  文档明确 `pip install -r backend/requirements.txt` 后还需运行 `scripts/install-collection-browser.ps1`；说明功能验证与正式采集差异、授权前提、`.runtime` 数据位置、JSONL 格式和不得提交的数据。将“双研究系统”当前描述更新为“三个功能子系统”，但不改写历史验收记录。

- [ ] **Step 2: 新增 ADR-0002**

  记录“独立平台子系统”相对于“放入多准则数据中心”和“外部独立工具”的取舍；注明采集数据是共享只读资产，研究处理状态归各研究系统所有。

- [ ] **Step 3: 运行后端完整测试**

  Run: `& 'E:\anaconda927\envs\py311\python.exe' -m pytest backend/tests -q`

  Expected: PASS，且测试无网络请求。

- [ ] **Step 4: 运行前端完整单元测试**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' test -- --run`

  Expected: PASS。

- [ ] **Step 5: 运行前端设计契约**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' run check:design`

  Expected: PASS。

- [ ] **Step 6: 运行前端格式检查**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' run format:check`

  Expected: PASS。

- [ ] **Step 7: 运行 TypeScript 类型检查**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' run typecheck`

  Expected: PASS。

- [ ] **Step 8: 运行前端生产构建**

  Workdir: `frontend`

  Run: `& 'E:\aaaxz\nodejs0324\npm.cmd' run build`

  Expected: PASS。

- [ ] **Step 9: 安装与锁定包匹配的 Chromium**

  Run: `.\scripts\install-collection-browser.ps1 -PythonExe 'E:\anaconda927\envs\py311\python.exe'`

  Expected: Playwright Chromium 安装成功；若已安装则幂等完成。

- [ ] **Step 10: 执行受控人工联网冒烟验证**

  使用独立临时数据库启动网站，创建最多 3 个车系、每车系最多 2 页的功能验证任务。检查真实车系 ID/名称、完整原始对象、暂停/继续、重复执行去重和 JSONL；不得切换正式模式。若出现 403、429 或验证页面，记录自动暂停证据并停止验证。

- [ ] **Step 11: 执行真实浏览器桌面与窄屏验收**

  在 `1440×1000` 和 `390×844` 验证三个平级入口、四页导航、任务对话框、进度状态、车系查询、评论详情、键盘焦点和整页无横向溢出。检查控制台无未处理异常、网络无意外 404/500。截图只写入已忽略的 `output/playwright/collection/`。

- [ ] **Step 12: 写入真实验收记录**

  `docs/评论数据采集系统验收记录.md` 只记录实际执行的命令、结果、联网范围、采集数量、停止原因和截图路径；不声称运行过完整 500 车系任务。

- [ ] **Step 13: 检查新增文档没有占位**

  Run: `rg -n "TBD|TODO|待补充|以后再写" README.md AGENTS.md docs backend frontend/src scripts`

  Expected: 无本次新增占位。

- [ ] **Step 14: 检查补丁格式**

  Run: `git diff --check`

  Expected: 无格式错误。

- [ ] **Step 15: 检查工作区提交边界**

  Run: `git status --short`

  Expected: 不包含 `.runtime/`、采集数据、JSONL、浏览器会话、`frontend/dist/` 或截图。

- [ ] **Step 16: 提交文档和验收记录**

  ```powershell
  git add AGENTS.md README.md docs frontend/scripts/check-design-contract.mjs
  git commit -m "docs(collection): document operation and acceptance"
  ```

- [ ] **Step 17: 请求整分支代码审查并处理结论**

  使用 `superpowers:requesting-code-review` 检查规格覆盖、数据无损性、线程生命周期、状态竞争、域名允许列表、用户界面可访问性和文档一致性；修复高优先级问题后重新运行受影响门禁。

- [ ] **Step 18: 执行完成前证据核验**

  使用 `superpowers:verification-before-completion` 重新读取本次运行结果，确认每项完成声明均有当前证据。

---

## Implementation Completion Criteria

- Tasks 1–10 的复选项全部有实际证据，不以计划文字代替运行结果。
- 离线自动化门禁全部通过，真实联网验证严格限制在功能验证范围。
- 一条真实评论能从汽车之家适配器无损进入 SQLite、详情 API、Vue 详情页和 JSONL。
- 任务在暂停、重启、恢复、重复页、临时错误、403/429 和单车系失败下符合规格状态机。
- 三个子系统入口和 Collection 四页在桌面与手机宽度可操作。
- 文档、API、类型、测试和界面使用相同术语与字段。
- Git 历史由小型原子提交组成，工作区不含运行数据、凭据或无关变更。
