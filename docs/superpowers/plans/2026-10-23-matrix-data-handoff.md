# Matrix Data Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the version-safe handoff from review annotations to an immutable model dataset visible in Data Center.

**Architecture:** Add a project/schema-scoped handoff query in the review-analysis backend and make materialization verify an optional compatible target schema. Keep cross-page orchestration in the existing MCDM workspaces; render one compact pipeline status in Data Center and use the global schema selection as the single source of truth.

**Tech Stack:** Python 3.11, FastAPI 0.128.8, SQLite, Vue 3.5, TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-23-matrix-data-handoff-design.md`

## Global Constraints

- Never fabricate or infer missing sales; blockers remain strict.
- Reuse annotations only when deterministic schema fingerprints match.
- Preserve source job/schema lineage for every cross-version materialization.
- Keep review-analysis state in its module workspace and shared project/schema state in the MCDM workspace.
- Do not add runtime dependencies.

## Review Focus

- A schema with no exact job but an identical frozen predecessor must expose one compatible candidate, not all project jobs.
- A same-project schema with different criteria must reject cross-version materialization.
- A job with blockers must remain non-materializable even when a compatible target is supplied.
- Switching schema while requests are in flight must not render the previous version's handoff.
- An existing manually imported dataset must remain the authoritative Data Center dataset.

---

### Task 1: Version-safe backend handoff

**Files:**
- Modify: `backend/review_analysis/repository.py`
- Modify: `backend/review_analysis/matrix.py`
- Modify: `backend/review_analysis/api.py`
- Test: `backend/tests/test_review_analysis_api.py`
- Test: `backend/tests/test_review_analysis_repository.py`

**Interfaces:**
- Produces: `GET /api/projects/{project_id}/review-analysis/handoff?schema_id=...`
- Produces: `POST .../jobs/{job_id}/datasets` accepting `{ "target_schema_id": string | null }`
- Produces: dataset lineage persisted in `review_matrix_dataset_lineage`

- [x] Write failing API/repository tests for exact jobs, compatible fingerprint reuse, incompatible rejection, strict blockers and lineage.
- [x] Run the focused tests and confirm RED for missing contracts.
- [x] Implement the minimal repository, matrix service and FastAPI contracts.
- [x] Run focused backend tests and confirm GREEN.
- [x] Commit the backend slice.

### Task 2: Current-version review analysis workspace

**Files:**
- Modify: `frontend/src/modules/mcdm/review-analysis/api.ts`
- Modify: `frontend/src/modules/mcdm/review-analysis/workspace.ts`
- Modify: `frontend/src/modules/mcdm/views/ReviewAnalysisView.vue`
- Test: `frontend/src/modules/mcdm/review-analysis/workspace.spec.ts`

**Interfaces:**
- Consumes: schema-filtered job listing and target-schema materialization from Task 1.
- Produces: only current-schema jobs in ordinary history; compatible handoff remains explicitly labelled.

- [x] Write failing Vitest cases for schema-scoped job loading and target-schema materialization.
- [x] Run the focused test and confirm RED.
- [x] Implement typed API/workspace changes and version labels.
- [x] Run the focused test and confirm GREEN.
- [x] Commit the frontend state slice.

### Task 3: Data Center pipeline status and global version control

**Files:**
- Modify: `frontend/src/modules/mcdm/workspace.ts`
- Modify: `frontend/src/modules/mcdm/McdmWorkbench.vue`
- Modify: `frontend/src/modules/mcdm/views/CriteriaView.vue`
- Modify: `frontend/src/modules/mcdm/views/DataView.vue`
- Modify: `frontend/src/styles/pages.css`
- Test: `frontend/src/modules/mcdm/workspace.spec.ts`
- Test: `frontend/src/modules/collection/collectionViews.spec.ts`

**Interfaces:**
- Consumes: handoff endpoint and materialization contract from Task 1.
- Produces: `matrixHandoff`, `loadMatrixHandoff()`, `materializeHandoff()` and a global schema selector.

- [x] Write failing workspace/source-contract tests for loading, stale-response protection, action routing and refresh after materialization.
- [x] Run focused frontend tests and confirm RED.
- [x] Implement the workspace orchestration, global selector and compact Data Center handoff card.
- [x] Run focused frontend tests and confirm GREEN.
- [x] Commit the Data Center slice.

### Task 4: Documentation and end-to-end verification

**Files:**
- Modify: `docs/开发与架构规范.md`
- Modify: `docs/测试与质量门禁.md` only if commands or acceptance coverage change.

**Interfaces:**
- Consumes: completed Tasks 1-3.
- Produces: documented version compatibility, strict blocker and lineage rules.

- [x] Update architecture documentation with the completed handoff.
- [x] Run backend affected tests, full frontend tests, format check, typecheck and build.
- [x] Verify the real browser flow at desktop and narrow viewport with the local runtime database.
- [x] Commit documentation and verification fixes.
