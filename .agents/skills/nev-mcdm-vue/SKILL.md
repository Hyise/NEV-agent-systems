---
name: nev-mcdm-vue
description: "Use when modifying Vue single-file components, frontend workspace/composables, ECharts view configuration, shared frontend state, or navigation in the NEV MCDM project. Do not use for backend-only, algorithm-only, or documentation-only changes."
---

# NEV MCDM Vue Boundaries

Keep the research workbench understandable as features are added. Preserve explicit ownership instead of growing a page-sized monolith.

## Workflow

1. Read `frontend/src/App.vue`, `workspace.ts`, `api.ts`, the affected view, and `Chart.vue` only when chart behavior changes.
2. Identify the owner of every new concern before editing:
   - `App.vue`: application shell, navigation, page selection, global dialogs and status surfaces.
   - `views/*.vue`: one business page's presentation and page-local derived data.
   - `workspace.ts`: cross-page state, orchestration, loading/error state and shared actions.
   - `api.ts`: HTTP transport plus shared request/response TypeScript contracts.
   - `Chart.vue`: reusable ECharts initialization, resize, accessibility and disposal.
3. Extend an existing boundary when it remains cohesive. Extract a component or composable when a concern has its own lifecycle, is reused, or makes its owner difficult to review. Do not extract wrappers that only rename markup.
4. Keep one source of truth. Do not mirror server or shared state in multiple views. Keep request concurrency protection and user-visible errors in the workspace layer.
5. Put business chart options in the view; keep generic chart lifecycle in `Chart.vue`. Supply an accurate accessible label.
6. Preserve strict TypeScript types, keyboard behavior, responsive layout, unsaved-change protection, and async loading for secondary views.

Read [project conventions](references/project-conventions.md) before structural changes or when ownership is unclear.

## Verification

From `frontend/`, run:

```powershell
npm.cmd run format:check
npm.cmd run typecheck
npm.cmd run build
```

For visible or interactive changes, also exercise the affected flow in a real browser at desktop and narrow viewport sizes. Report any check that could not run.
