# Tabular Review Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 支持从真实汽车之家 CSV/XLSX 文件批量导入完整“分项评论全文”，并在资产查阅与大模型分析中使用该正文。

**Architecture:** 后端标准库解析原始文件并复用既有资产校验/事务写入；前端 API 传输文件，workspace 编排多文件预检和确认，对话框展示逐文件结果。既有 JSON/JSONL 对象接口保持兼容。

**Tech Stack:** Python 3.11 标准库、FastAPI/Pydantic、SQLite、Vue 3、TypeScript、Vitest。

**Spec:** `docs/superpowers/specs/2026-10-17-tabular-review-import-design.md`

## Global Constraints

- 不修改、不复制或提交用户提供的 116 个原始评论文件。
- 不新增运行依赖；XLSX/CSV 使用 Python 标准库解析。
- 原始评论只读保存；“分项评论全文”不得拆分、拼接或改写。
- 既有 JSON/JSONL 导入 API 保持兼容。
- 本机服务继续只监听 `127.0.0.1`。

## Review Focus

- XLSX 使用共享字符串、内联字符串或缺少空白单元格时，列对齐必须保持正确。
- `koubei_id` 为空时，必须稳定使用 `show_id` 且不能产生随机重复身份。
- UTF-8 BOM、GB18030 CSV 和带逗号/换行的正文必须完整读取。
- 15.86 MB / 14,183 行样本必须处于明确限制内，不得再触发旧上限。
- 多文件中任一文件校验失败时，不得开放确认写入。

---

### Task 1: 表格解析与正文契约

**Files:**
- Create: `backend/collection/import_file.py`
- Modify: `backend/review_analysis/text.py`
- Modify: `frontend/src/modules/collection/reviewContent.ts`
- Test: `backend/tests/test_review_import_file.py`
- Test: `backend/tests/test_review_analysis_domain.py`
- Test: `frontend/src/modules/collection/reviewContent.spec.ts`

**Interfaces:**
- Produces: `parse_review_import_file(filename: str, payload: bytes) -> list[dict[str, Any]]`。
- Produces: `extract_analysis_text()` 和 `buildReadableReview()` 优先读取“分项评论全文”。

- [ ] 写 CSV/XLSX 映射、缺列、正文保留、日期、ID 回退和正文读取的失败测试。
- [ ] 运行定向测试并确认因解析器/新正文键缺失而失败。
- [ ] 实现标准库 CSV/XLSX 解析和正文兼容。
- [ ] 运行定向测试并确认通过。

### Task 2: 原始文件校验与确认 API

**Files:**
- Modify: `backend/collection/asset_service.py`
- Modify: `backend/collection/asset_api.py`
- Test: `backend/tests/test_review_asset_import.py`
- Test: `backend/tests/test_review_asset_api.py`

**Interfaces:**
- Consumes: `parse_review_import_file(filename, payload)`。
- Produces: `POST /api/collection/review-assets/import-file/validate` 与 `POST /api/collection/review-assets/import-file`。

- [ ] 写原始文件预检/确认、大小与条数边界、指纹变化的失败测试。
- [ ] 运行定向测试并确认新路由不存在或旧上限导致失败。
- [ ] 实现文件服务方法、限制和 HTTP 边界，保留旧接口。
- [ ] 运行后端相关测试并确认通过。

### Task 3: 多文件导入工作流

**Files:**
- Modify: `frontend/src/modules/collection/api.ts`
- Modify: `frontend/src/modules/collection/assetWorkspace.ts`
- Modify: `frontend/src/modules/collection/components/ReviewImportDialog.vue`
- Modify: `frontend/src/modules/collection/importFile.ts`
- Test: `frontend/src/modules/collection/assetWorkspace.spec.ts`
- Test: `frontend/src/modules/collection/collectionViews.spec.ts`

**Interfaces:**
- Consumes: 文件校验/确认 API。
- Produces: `validateImportFiles(files: File[])`、逐文件预览状态和 `confirmImport()`。

- [ ] 写多文件先全部校验、错误阻止确认、顺序确认与汇总结果的失败测试。
- [ ] 运行前端定向测试并确认因新工作流缺失而失败。
- [ ] 实现 API、workspace 和对话框交互，支持 `.json/.jsonl/.csv/.xlsx` 多选。
- [ ] 运行前端相关测试并确认通过。

### Task 4: 文档、真实样本只读验收与总验证

**Files:**
- Modify: `docs/API与数据契约.md`
- Modify: `docs/运行须知.md`
- Modify: `docs/测试与质量门禁.md`
- Modify: `docs/评论数据采集系统验收记录.md`

**Interfaces:**
- Consumes: Tasks 1–3 的稳定接口和 UI。

- [ ] 更新格式、字段、限制、多文件流程和只读原始数据说明。
- [ ] 使用真实小型 XLSX 做只读解析和浏览器预检，不确认写入。
- [ ] 运行后端全量测试、前端测试、设计检查、格式检查、类型检查和构建。
- [ ] 在桌面与窄屏检查导入对话框并重启 8029 服务。

