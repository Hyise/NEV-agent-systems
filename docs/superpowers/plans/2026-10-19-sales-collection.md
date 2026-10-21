# 销量数据采集 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在评论数据工作台中增加可追溯的月度销量采集、入库、匹配、查询与导出流程。

**Architecture:** 新建 `backend/sales_collection/` 垂直模块，使用独立 SQLite 表和单工作器，并与现有评论采集共享外部访问预约。前端新增独立 `salesWorkspace.ts` 与 `SalesView.vue`，只通过销量 API 读取状态。

**Tech Stack:** Python 3.11、FastAPI 0.128.8、SQLite、httpx 0.28.1、Vue 3.5、TypeScript 5.9、Vitest 5。

**Spec:** `docs/销量数据采集系统设计.md`

## Global Constraints

- 全国车系月度零售量；来源平台、月份和车系为最小数据粒度。
- 三平台结果分别保存；缺失不是零，禁止跨平台冒充或平均。
- 不绕过验证码、登录或访问限制；受阻步骤必须留下可见错误。
- 不修改评论原始数据，不提交运行数据库、采集结果或浏览器会话。
- 外部访问必须经过现有协调器；真实联网测试只用一个月份。

## Review Focus

- 非法月份或起止倒置必须在 API 边界被拒绝。
- 重复运行同一平台同一月份必须幂等更新，不能制造重复记录。
- 某平台失败时其他平台月份仍能完成，任务终态为部分失败。
- 平台返回空列表或月份错位必须视为结构错误，而不是成功零销量。
- CSV 文本字段以公式字符开头时必须转义。

---

### Task 1: 销量领域与持久化

**Files:**
- Create: `backend/sales_collection/domain.py`
- Create: `backend/sales_collection/repository.py`
- Create: `backend/tests/test_sales_collection_repository.py`

**Interfaces:**
- Produces: `SalesCollectionRepository`, `CreateSalesJobBody`, `SalesRecord`, `SalesSourceError`。

- [ ] 编写失败测试：月份范围校验、任务步骤、记录幂等写入、评论车系精确匹配和筛选分页。
- [ ] 运行 `python -m pytest backend/tests/test_sales_collection_repository.py -q`，确认因模块缺失而失败。
- [ ] 实现最小领域对象、迁移和仓储查询。
- [ ] 重跑目标测试并确认通过。

### Task 2: 平台适配器与任务服务

**Files:**
- Create: `backend/sales_collection/adapters.py`
- Create: `backend/sales_collection/service.py`
- Create: `backend/tests/fixtures/sales/autohome-page-1.json`
- Create: `backend/tests/test_sales_collection_adapters.py`
- Create: `backend/tests/test_sales_collection_service.py`
- Modify: `backend/collection/coordination.py`

**Interfaces:**
- Consumes: `SalesCollectionRepository.save_month_records(...)`。
- Produces: `AutohomeSalesAdapter.fetch_month(month)`、`SalesCollectionService.start(job_id)`。

- [ ] 编写失败测试：汽车之家分页解析、空页/错月拒绝、平台失败隔离和预约释放。
- [ ] 运行目标测试，确认正确失败。
- [ ] 实现低频分页适配器、受阻平台适配器和单工作器服务。
- [ ] 重跑适配器与服务测试并确认通过。

### Task 3: FastAPI 契约与应用装配

**Files:**
- Create: `backend/sales_collection/api.py`
- Create: `backend/tests/test_sales_collection_api.py`
- Modify: `backend/app.py`

**Interfaces:**
- Produces: `/api/sales-collection/overview`、`/jobs`、`/records`、`/export`。

- [ ] 编写失败 API 测试：创建、冲突、详情、筛选和安全 CSV 导出。
- [ ] 运行目标测试，确认路由不存在导致失败。
- [ ] 装配仓储、服务和路由，关闭应用时释放工作器。
- [ ] 重跑 API 测试并确认通过。

### Task 4: 销量数据工作台

**Files:**
- Create: `frontend/src/modules/collection/salesWorkspace.ts`
- Create: `frontend/src/modules/collection/salesWorkspace.spec.ts`
- Create: `frontend/src/modules/collection/views/SalesView.vue`
- Modify: `frontend/src/modules/collection/api.ts`
- Modify: `frontend/src/modules/collection/CollectionWorkbench.vue`
- Modify: `frontend/src/modules/collection/collectionViews.spec.ts`
- Modify: `frontend/src/styles/collection.css`

**Interfaces:**
- Consumes: Task 3 的销量 API。
- Produces: “销量数据”导航、月份/平台任务表单、步骤状态、记录筛选和 CSV 下载。

- [ ] 编写失败测试：工作区并发保护、错误呈现、导航装配和受阻平台说明。
- [ ] 运行前端目标测试，确认新模块缺失而失败。
- [ ] 实现 API 类型、工作区、视图和响应式样式。
- [ ] 重跑前端目标测试并确认通过。

### Task 5: 文档同步与整体验证

**Files:**
- Modify: `docs/API与数据契约.md`
- Modify: `docs/开发与架构规范.md`
- Modify: `docs/运行须知.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: Tasks 1–4 的最终行为。

- [ ] 同步 API、运行限制、模块职责和用户流程。
- [ ] 运行后端完整测试。
- [ ] 运行前端测试、格式检查、类型检查和构建。
- [ ] 用一个月份执行汽车之家真实联网冒烟；仅报告实际得到的记录数。
- [ ] 在桌面与窄屏真实浏览器中验证销量页面。
