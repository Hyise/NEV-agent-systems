# Experiment Analysis Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect completed custom model experiments to the scenario and share analysis pages with explicit run, model, and month provenance.

**Architecture:** Persist BEAST monthly diagnostic curves inside the immutable experiment result, load a selected run's full detail only when needed, and derive both analysis pages from that selected detail. Preset projects retain their existing archive adapters.

**Tech Stack:** Python 3.11, FastAPI, NumPy/SciPy, Vue 3, TypeScript, Vitest, ECharts

**Spec:** `docs/superpowers/specs/2026-10-24-experiment-analysis-handoff-design.md`

## Global Constraints

- Do not modify raw reviews, raw sales records, or frozen matrix records.
- Preset archive behavior must remain unchanged.
- Custom results must be selected by immutable experiment ID; never silently publish “latest”.
- 2026 and later effective time pressure is exactly zero.
- Old runs without diagnostic curves must render an explicit compatibility state.

## Review Focus

- A completed list row has predictions omitted; selection must fetch run detail before rendering shares.
- Switching project, schema, or run must not leave stale detail visible.
- Runs without BEAST or without diagnostic metadata must not crash the scenario page.
- Multiple test months must remain separable and must not be renormalized together.
- Preset projects must continue to use the archive curves and predictions.

---

### Task 1: Persist BEAST monthly diagnostic curves

**Files:**
- Modify: `backend/model_experiments/models/beast.py`
- Modify: `backend/tests/test_model_experiment_engine.py`

**Interfaces:**
- Consumes: `DatasetSnapshot.records`, fitted BEAST parameters, `effective_time_pressure()`.
- Produces: `metadata["diagnostic_curves"]` with `weights` and `rationality` rows.

- [x] Add a failing engine test that asserts one row per observed month, criterion-complete values, and zero pressure for 2026 months.
- [x] Run the targeted backend test and observe the missing metadata failure.
- [x] Add the smallest diagnostic-curve calculation to `BeastMcdmModel.fit_predict`.
- [x] Run model experiment engine tests and confirm they pass.

### Task 2: Load selected experiment detail and expose result selectors

**Files:**
- Modify: `frontend/src/modules/mcdm/model-experiments/api.ts`
- Modify: `frontend/src/modules/mcdm/model-experiments/workspace.ts`
- Modify: `frontend/src/modules/mcdm/model-experiments/workspace.spec.ts`
- Create: `frontend/src/modules/mcdm/model-experiments/results.ts`
- Create: `frontend/src/modules/mcdm/model-experiments/results.spec.ts`

**Interfaces:**
- Consumes: `ModelExperimentApi.get(projectId, runId)` and completed run results.
- Produces: selected full run detail plus pure helpers for available models, months, predictions, and diagnostic curves.

- [x] Add failing workspace tests for detail loading, run switching, and stale-detail clearing.
- [x] Add failing helper tests for BEAST preference, month filtering, and absent diagnostics.
- [x] Implement detail loading and pure result selectors.
- [x] Run the targeted frontend tests and confirm they pass.

### Task 3: Render custom scenario and share results

**Files:**
- Modify: `frontend/src/modules/mcdm/views/ScenarioView.vue`
- Modify: `frontend/src/modules/mcdm/views/SharesView.vue`
- Modify: `frontend/src/modules/mcdm/views/ExperimentsView.vue`
- Modify: `frontend/src/styles/pages.css`
- Modify: `frontend/scripts/check-design-contract.mjs`

**Interfaces:**
- Consumes: selected full experiment detail and result selector helpers from Task 2.
- Produces: traceable run/model/month controls and rendered custom analysis evidence.

- [x] Add design-contract assertions for experiment provenance controls and explicit legacy-run messages; observe failure.
- [x] Implement custom run/model/month controls while retaining preset archive behavior.
- [x] Update experiment history selection to call the detail-loading action.
- [x] Run design contract, frontend tests, typecheck, formatting check, and production build.

### Task 4: Re-run current V3 experiment and verify the live workflow

**Files:**
- No source files; creates a new immutable runtime experiment record.

**Interfaces:**
- Consumes: project `3128ba93-af2f-49a4-b961-3fa01a51e10b`, schema `811eb8d4-ca57-4ad3-90cc-669239f81003`, V3 dataset.
- Produces: a completed run whose BEAST metadata contains monthly diagnostics.

- [x] Run the full backend test suite and all frontend verification commands.
- [x] Restart the current branch on port 8029.
- [x] Create one experiment with the established Ridge, Random Forest, and BEAST configuration and wait for terminal status.
- [x] Verify API detail contains 175 predictions per model and four BEAST diagnostic months.
- [x] Verify the live scenario and share pages receive non-empty selected-run data without changing raw data.
