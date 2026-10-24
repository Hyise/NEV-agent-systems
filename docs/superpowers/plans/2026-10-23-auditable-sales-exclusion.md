# Auditable Sales Exclusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow explicitly excluding objectively unavailable sales groups while preserving an immutable exclusion audit and sending the remaining records to model computation.

**Architecture:** Extend matrix materialization with an explicit exclusion policy; keep strict behavior as the default. Persist excluded groups beside dataset lineage in the same transaction, expose inclusion metadata through handoff/overview, and drive both Data Center and Review Analysis actions from the same typed contract.

**Tech Stack:** Python 3.11, FastAPI, SQLite, Vue 3, TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-23-auditable-sales-exclusion-design.md`

## Global Constraints

- Only `missing_sales` groups may be excluded.
- Never mutate raw reviews, annotations, sales, or an existing authoritative dataset.
- Default materialization remains strict.
- Persist dataset and exclusion audit atomically.
- Do not add runtime dependencies.

## Review Focus

- A mixed blocker set containing `missing_sales` plus another issue must remain rejected.
- An all-missing dataset must not create an empty model snapshot.
- Repeated requests must return the existing authoritative snapshot without changing its audit.
- Monthly shares must sum to one over included records after exclusions.
- Cross-version compatible materialization must bind exclusions to the target dataset and retain source lineage.

---

### Task 1: Backend exclusion policy and audit

**Files:**
- Modify: `backend/review_analysis/api.py`
- Modify: `backend/review_analysis/matrix.py`
- Modify: `backend/review_analysis/repository.py`
- Modify: `backend/app.py`
- Test: `backend/tests/test_review_analysis_api.py`
- Test: `backend/tests/test_platform.py`

**Interfaces:**
- Produces: `MaterializeBody.exclusion_policy: "strict" | "exclude_missing_sales"`.
- Produces: persisted `review_matrix_dataset_exclusions` rows and dataset metadata `included_count`, `excluded_count`, `source_group_count`, `coverage_rate`, `exclusions`.

- [x] Write failing tests for strict rejection, allowed missing-sales exclusion, mixed-blocker rejection, atomic audit, idempotency and overview metadata.
- [x] Run focused backend tests and confirm RED.
- [x] Implement the minimal policy validation, migration, transactional persistence and metadata reads.
- [x] Run focused backend tests and confirm GREEN.
- [x] Include the backend slice in the current feature-branch commit.

### Task 2: Data Center and review-analysis controls

**Files:**
- Modify: `frontend/src/modules/mcdm/api.ts`
- Modify: `frontend/src/modules/mcdm/workspace.ts`
- Modify: `frontend/src/modules/mcdm/review-analysis/api.ts`
- Modify: `frontend/src/modules/mcdm/review-analysis/workspace.ts`
- Modify: `frontend/src/modules/mcdm/views/DataView.vue`
- Modify: `frontend/src/modules/mcdm/review-analysis/components/MatrixHandoff.vue`
- Modify: `frontend/src/styles/pages.css`
- Test: `frontend/src/modules/mcdm/workspace.spec.ts`
- Test: `frontend/src/modules/mcdm/review-analysis/workspace.spec.ts`

**Interfaces:**
- Consumes: Task 1 exclusion policy and dataset audit fields.
- Produces: explicit confirmed exclusion action and post-generation exclusion summary/list.

- [x] Write failing workspace tests for policy payload, eligibility and refreshed materialized metadata.
- [x] Run focused frontend tests and confirm RED.
- [x] Implement typed API/workspace orchestration and concise UI states.
- [x] Run focused frontend tests, typecheck and design check; confirm GREEN.
- [x] Include the frontend slice in the current feature-branch commit.

### Task 3: Documentation and end-to-end verification

**Files:**
- Modify: `docs/开发与架构规范.md`
- Modify: `docs/测试与质量门禁.md`

**Interfaces:**
- Consumes: Tasks 1-2.
- Produces: reproducible exclusion-policy documentation and verified local runtime.

- [x] Document the exclusion boundary, monthly denominator and audit requirements.
- [x] Run full backend and frontend suites, format, design, typecheck and build.
- [x] Exercise the real 300-group dataset, verify 259 included / 41 excluded, then verify model pages load the snapshot.
- [x] Include documentation and verification fixes in the current feature-branch commit.

## Verification Result

- Dataset `评论标注矩阵-4e1c6f02-V2`: 300 source groups, 259 included, 41 excluded, 86.33% coverage.
- Exclusions are all `missing_sales`; raw reviews remain unchanged and the exclusion list is persisted beside dataset lineage.
- Local experiment `5589fade`: training 2026-01—02, validation 2026-03, test 2026-04; Ridge, Random Forest and BEAST-MCDM all completed.
- Automated gates: backend 344 passed; frontend 104 passed; typecheck, format, design contract and production build passed.
- Browser acceptance at `http://127.0.0.1:8029`: Data Center displays inclusion/exclusion audit and links to Model Experiments; the four-month form defaults to one validation and one test month.
