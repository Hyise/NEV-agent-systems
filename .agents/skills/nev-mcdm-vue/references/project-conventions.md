# Frontend project conventions

## Dependency direction

```text
main.ts -> App.vue -> views/*.vue -> Chart.vue
                       |       |
                       v       v
                  workspace.ts -> api.ts
```

- `main.ts` mounts the application and imports global styles.
- `App.vue` creates and provides one workspace. It selects asynchronously loaded views and owns shell-level navigation/dialogs.
- A view consumes the workspace with `useWorkspace()`. It may calculate presentation-only values but should not recreate shared request or persistence logic.
- `workspace.ts` may call `api.ts`; `api.ts` must not know about Vue components or workspace state.
- `Chart.vue` receives a typed ECharts option and accessible label. It does not know project, schema, month, criterion, or model semantics.

Avoid circular imports. A lower-level module must not import a page or `App.vue`.

## Change rules

### Add a page

1. Add the page name to the `Page` union in `workspace.ts`.
2. Create `views/<Name>View.vue` and load it with `defineAsyncComponent` in `App.vue`.
3. Extend navigation and the page-to-component map in one change.
4. Put cross-page data/actions in the workspace and page-only computed presentation in the view.

### Add shared state or an API operation

- Prefer a typed `ref`/`computed` and named action in `workspace.ts`.
- Keep response contracts explicit in `api.ts`; do not use `any` or cast an unvalidated shape merely to silence TypeScript.
- Preserve the request-token pattern when responses may arrive out of order.
- Convert technical failures into one actionable Chinese user message at the orchestration boundary.

### Add a chart

- Build the business option as `computed` in the owning view.
- Reuse `Chart.vue` for ECharts setup, `ResizeObserver`, redraw and disposal.
- Register a new ECharts chart/component centrally only when required.
- Do not animate analytical results by default; prioritise legibility and reproducibility.

### Split code

Split when a file mixes owners, a block has a distinct lifecycle, or a unit is reused. Line count is a warning, not a quota. Avoid generic `utils.ts` dumping grounds and one-line wrapper components.

## User-interface invariants

- All interactive controls have an accessible name and visible focus state.
- Dialog open/close restores focus; destructive actions require an explicit confirmation path.
- Narrow layouts remain usable without horizontal page scrolling, except intentional data tables.
- Do not invent analysis results. Display only values returned by the backend or clearly labelled demo/input data.
