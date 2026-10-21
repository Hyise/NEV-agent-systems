# Live Review Research Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a live, operable review-annotation workflow that can turn completed annotations into an immutable model-experiment dataset.

**Architecture:** Keep HTTP contracts in the review-analysis API, aggregation and persistence in a focused backend service, cross-page orchestration in Vue workspaces, and presentation in small components. Poll jobs and job-scoped annotations together, then explicitly preview and materialize a dataset before navigating to model experiments.

**Tech Stack:** FastAPI, Pydantic, SQLite, Vue 3 Composition API, TypeScript, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-10-21-live-review-research-workflow.md`

## Global Constraints

- Original reviews are immutable; generated annotations and datasets are separate records.
- Preset projects remain read-only.
- One active LLM job globally.
- Generated datasets must satisfy the existing model experiment dataset contract.
- Integrate into local `main` only after the full verification suite passes; do not push.

## Review Focus

- A removed project id in local storage falls back without breaking initial load.
- Project/schema switches cannot apply stale polling responses.
- A job with missing review dates or criteria produces preview blockers rather than malformed records.
- Multiple-platform sales select the documented deterministic platform priority.
- A completed job with retry children does not duplicate a review in the generated matrix.

---

### Task 1: Persist research context and expose complete annotation controls

**Files:**
- Modify: `frontend/src/modules/mcdm/workspace.ts`
- Modify: `frontend/src/modules/mcdm/review-analysis/api.ts`
- Modify: `frontend/src/modules/mcdm/review-analysis/workspace.ts`
- Modify: `frontend/src/modules/mcdm/review-analysis/components/SourceScopePanel.vue`
- Test: `frontend/src/modules/mcdm/review-analysis/workspace.spec.ts`
- Test: `frontend/src/modules/mcdm/workspace.spec.ts`

**Interfaces:**
- Produces: job-scoped live refresh, `reviewDateFrom`, `reviewDateTo`, `annotationSampling`, persisted project selection.

- [ ] Write failing tests for date/sampling request fields, automatic job result selection, live result refresh, stale response protection and project persistence fallback.
- [ ] Run focused Vitest tests and confirm failures.
- [ ] Implement the minimal workspace/API changes.
- [ ] Run focused Vitest tests and confirm success.

### Task 2: Store immutable review dates and build matrix previews

**Files:**
- Modify: `backend/review_analysis/domain.py`
- Modify: `backend/review_analysis/repository.py`
- Create: `backend/review_analysis/matrix.py`
- Modify: `backend/review_analysis/api.py`
- Modify: `backend/app.py`
- Test: `backend/tests/test_review_analysis_matrix.py`
- Test: `backend/tests/test_review_analysis_api.py`

**Interfaces:**
- Produces: `GET /jobs/{job_id}/matrix-preview` and `POST /jobs/{job_id}/datasets`, returning preview blockers or immutable dataset metadata.
- Consumes: frozen criteria, job snapshots/results, matched sales records, existing `datasets` table.

- [ ] Write failing tests for snapshot dates, aggregation probabilities, sales priority, blockers, duplicate retry snapshots and dataset persistence.
- [ ] Run focused pytest tests and confirm failures.
- [ ] Implement matrix builder, schema migration and API endpoints.
- [ ] Run focused pytest tests and confirm success.

### Task 3: Present the live task and matrix handoff

**Files:**
- Modify: `frontend/src/modules/mcdm/review-analysis/api.ts`
- Modify: `frontend/src/modules/mcdm/review-analysis/workspace.ts`
- Modify: `frontend/src/modules/mcdm/views/ReviewAnalysisView.vue`
- Modify: `frontend/src/modules/mcdm/review-analysis/components/AnnotationResults.vue`
- Create: `frontend/src/modules/mcdm/review-analysis/components/MatrixHandoff.vue`
- Modify: `frontend/src/styles/pages.css`
- Test: `frontend/src/modules/mcdm/review-analysis/workspace.spec.ts`
- Test: `frontend/src/modules/mcdm/review-analysis/reviewAnalysisViews.spec.ts`

**Interfaces:**
- Produces: accessible progress/status controls, live result list, matrix preview/save action and an experiments navigation action.

- [ ] Write failing view/workspace tests for live progress, result refresh, preview blockers, save success and experiments navigation.
- [ ] Run focused Vitest tests and confirm failures.
- [ ] Implement the components and workspace actions without duplicating server state in views.
- [ ] Run focused Vitest tests and confirm success.

### Task 4: Documentation, regression verification and integration

**Files:**
- Modify: `docs/API与数据契约.md`
- Modify: `docs/运行须知.md`
- Modify: `docs/系统设计与实施路线.md`

- [ ] Document the live workflow, aggregation rules, endpoints and local startup/verification path.
- [ ] Run backend pytest suite.
- [ ] Run frontend format check, typecheck, tests and production build.
- [ ] Exercise the workflow in a real browser at desktop and narrow widths.
- [ ] Commit logically grouped changes on `feat/raw-review-reader`.
- [ ] Merge into local `main` and rerun backend/frontend verification on the merged tree.
