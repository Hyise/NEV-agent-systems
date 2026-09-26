# Scenario checks

These checks are reviewed whenever the Skill or frontend architecture changes.

## RED baseline observed before the Skill

Before the existing frontend refactor, `App.vue` reached 1476 lines and mixed navigation, requests, shared state, six business pages, and charts. No project-level Vue Skill identified ownership boundaries. The current `App.vue` is an application shell; the Skill must prevent regression to the earlier structure.

## Expected trigger scenarios

1. **Add a seventh business page** — extend the `Page` union and shell mapping, create an async `views/*View.vue`, and keep page markup/requests out of `App.vue`.
2. **Share one filter across two pages** — establish one state owner in `workspace.ts` or a cohesive composable instead of duplicating drifting refs.
3. **Add an ECharts business visualization** — compute business options in the page while `Chart.vue` retains setup, resize, accessibility, redraw and disposal.

## Expected non-trigger scenarios

1. A backend-only Pydantic validator or FastAPI route change uses backend guidance, not this Skill.
2. A documentation-only spelling correction does not require this Skill.

## Pass criteria

- The description distinguishes all positive and negative scenarios.
- The instructions assign ownership for the shell, views, workspace, HTTP transport, and chart lifecycle.
- The instructions require the project's format, type, build, and relevant browser checks without loading unrelated references for simple edits.

## 2026-09-26 manual evaluation

- All three trigger scenarios route to the expected owner in `SKILL.md` and `references/project-conventions.md`.
- Both negative scenarios are excluded by the frontmatter description.
- A structural check confirmed every required boundary and validation command is present; `quick_validate.py` passed.
- This task did not authorize sub-agent delegation, so scenario evaluation was performed directly and is recorded here rather than presented as an independent review.
