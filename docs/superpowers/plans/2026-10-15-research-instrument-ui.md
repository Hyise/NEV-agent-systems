# Research Instrument UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the current platform, collection, and MCDM presentation as a coherent research-instrument interface without changing routes, API contracts, research data, or workspace ownership.

**Architecture:** Keep the existing Vue module boundaries and six CSS layers. First establish shared tokens and interaction primitives, then reshape the platform hierarchy, then update both workbench shells and their domain surfaces. Use the existing static design contract plus Vitest for regression gates, and real-browser Playwright checks for rendered behavior.

**Tech Stack:** Vue 3.5.22, TypeScript 5.9.3, Vue Router 4.6.4, Lucide Vue 0.468.0, ECharts 6.0.0, CSS, Vitest 5.0.2, Playwright CLI.

**Spec:** `docs/superpowers/specs/2026-10-15-research-instrument-ui-design.md`

## Global Constraints

- Preserve all backend APIs, hash routes, research values, data ownership, loading/error behavior, and immutable original-review rules.
- Keep `SimSun, "宋体", STSong, "Songti SC", serif` for brand and research headings; use the local Chinese UI sans-serif chain for controls, body copy, and dense data.
- Do not add runtime dependencies, web fonts, gradients, glass effects, or decorative chart animation.
- Keep the adaptive module planning-only: no form, sample metric, or API call.
- Use only purposeful motion under 300ms, never `transition: all` or `scale(0)`; respect `prefers-reduced-motion` and fine-pointer hover media queries.
- Keep one workspace owner per module and preserve async page loading, focus restoration, visible focus, and narrow-screen table scrolling.

## Review Focus

- A 390px viewport must not gain page-level horizontal scrolling; tables may scroll inside their own regions.
- Long project and series names must truncate or wrap without covering controls or changing the active-navigation hit target.
- Native dialogs and the mobile navigation must restore focus and remain usable with reduced motion enabled.
- Empty, loading, error, planned, and read-only states must remain distinguishable without relying on color alone.
- Dense comment text, four-digit catalog counts, and 200% browser zoom must remain readable without clipping primary actions.

---

### Task 1: Shared visual tokens and interaction primitives

**Files:**
- Modify: `frontend/scripts/check-design-contract.mjs`
- Modify: `frontend/src/styles/foundation.css`
- Modify: `frontend/src/styles/components.css`
- Modify: `frontend/src/styles/shell.css`

**Interfaces:**
- Consumes: existing CSS layer order from `frontend/src/style.css`.
- Produces: stable font, color, spacing, easing, focus, active-press, dialog, drawer, and hover primitives used by Tasks 2–5.

- [ ] **Step 1: Extend the design contract before implementation**

Add expectations for the approved canvas/surface/ink tokens, the UI sans-serif body chain, `--ease-out`, `--ease-in-out`, `.btn:active`, fine-pointer hover gating, and a reduced-motion override that removes transform motion.

- [ ] **Step 2: Run the design contract and verify RED**

Run: `npm.cmd run check:design`

Expected: FAIL because the new tokens and interaction rules are absent.

- [ ] **Step 3: Implement the shared visual foundation**

Update `foundation.css` with the approved palette, title/body/data font roles, easing variables, restrained radii and focus treatment. Update `components.css` and `shell.css` so pressable elements use exact-property transitions, `scale(0.98)` press feedback, fine-pointer hover rules, origin-appropriate dialog/drawer motion, and reduced-motion-safe behavior.

- [ ] **Step 4: Verify GREEN and regression safety**

Run: `npm.cmd run check:design`

Expected: `Design contract passed.`

Run: `npm.cmd test -- --run`

Expected: all frontend tests pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/scripts/check-design-contract.mjs frontend/src/styles/foundation.css frontend/src/styles/components.css frontend/src/styles/shell.css
git commit -m "feat(frontend): establish research instrument design tokens"
```

### Task 2: Platform directory and adaptive planning hierarchy

**Files:**
- Modify: `frontend/scripts/check-design-contract.mjs`
- Modify: `frontend/src/platform/PlatformHome.vue`
- Modify: `frontend/src/platform/AdaptiveIntroduction.vue`
- Modify: `frontend/src/styles/platform.css`
- Test: `frontend/src/platform/modules.spec.ts`

**Interfaces:**
- Consumes: Task 1 tokens and the unchanged `researchModules` contract.
- Produces: a dominant MCDM entry, upstream collection entry, low-emphasis adaptive planning strip, and the shared evidence-chain visual.

- [ ] **Step 1: Write the failing platform contract**

Extend the design contract to require `platform-evidence-chain`, distinct collection/MCDM entry classes, an `adaptive-entry`, and the visible chain labels “发现车系”, “原始评论”, “准则证据”, “决策复核”. Keep the existing module-order unit test unchanged to prove routes and metadata remain stable.

- [ ] **Step 2: Run the focused checks and verify RED**

Run: `npm.cmd run check:design`

Expected: FAIL on the missing platform hierarchy and evidence-chain structure.

Run: `npm.cmd test -- --run src/platform/modules.spec.ts`

Expected: existing module contract remains PASS.

- [ ] **Step 3: Implement the platform hierarchy**

Reshape `PlatformHome.vue` into the approved upstream-data/core-research layout and separate adaptive planning strip. Simplify each available module to its role, three concise capabilities, status and one action. Restyle `AdaptiveIntroduction.vue` as a restrained research-onboarding document without adding controls or data.

- [ ] **Step 4: Verify GREEN**

Run: `npm.cmd run check:design`

Expected: `Design contract passed.`

Run: `npm.cmd test -- --run src/platform/modules.spec.ts src/router/index.spec.ts`

Expected: both files pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/scripts/check-design-contract.mjs frontend/src/platform/PlatformHome.vue frontend/src/platform/AdaptiveIntroduction.vue frontend/src/styles/platform.css frontend/src/platform/modules.spec.ts
git commit -m "feat(frontend): reshape platform as research evidence chain"
```

### Task 3: Shared workbench navigation and context shell

**Files:**
- Modify: `frontend/scripts/check-design-contract.mjs`
- Modify: `frontend/src/modules/collection/CollectionWorkbench.vue`
- Modify: `frontend/src/modules/mcdm/McdmWorkbench.vue`
- Modify: `frontend/src/components/AppBrand.vue`
- Modify: `frontend/src/styles/shell.css`
- Test: `frontend/src/modules/collection/collectionViews.spec.ts`

**Interfaces:**
- Consumes: Task 1 primitives and existing collection/MCDM workspace instances.
- Produces: a shared 208px desktop shell, icon-assisted navigation metadata, clearer active state, compact header/context behavior, and unchanged focus/navigation semantics.

- [ ] **Step 1: Write the failing shell contract**

Require both workbenches to render Lucide icons from their existing local page definitions, expose a semantic navigation label, keep `aria-current`, and retain exactly one workspace constructor call per module. Add a regression assertion that collection/MCDM state ownership counts remain one.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `npm.cmd test -- --run src/modules/collection/collectionViews.spec.ts`

Expected: FAIL because icon-assisted navigation is not yet rendered.

Run: `npm.cmd run check:design`

Expected: FAIL on the new shell expectations.

- [ ] **Step 3: Implement both shells**

Add stable Lucide icons to local navigation definitions and render them beside labels. Update the brand lockup, active-navigation treatment, compact platform bar, MCDM research-context toolbar and mobile drawer presentation. Preserve all existing event handlers, `KeepAlive`, focus restoration, unsaved-change protection and workspace construction.

- [ ] **Step 4: Verify GREEN**

Run: `npm.cmd test -- --run src/modules/collection/collectionViews.spec.ts`

Expected: focused test file passes.

Run: `npm.cmd run check:design`

Expected: `Design contract passed.`

- [ ] **Step 5: Commit**

```powershell
git add frontend/scripts/check-design-contract.mjs frontend/src/modules/collection/CollectionWorkbench.vue frontend/src/modules/mcdm/McdmWorkbench.vue frontend/src/components/AppBrand.vue frontend/src/styles/shell.css frontend/src/modules/collection/collectionViews.spec.ts
git commit -m "feat(frontend): unify research workbench navigation"
```

### Task 4: Collection workflow and asset surfaces

**Files:**
- Modify: `frontend/scripts/check-design-contract.mjs`
- Modify: `frontend/src/modules/collection/components/GuidedStageBar.vue`
- Modify: `frontend/src/modules/collection/views/AcquireView.vue`
- Modify: `frontend/src/modules/collection/views/AssetsView.vue`
- Modify: `frontend/src/modules/collection/views/ResearchHandoffView.vue`
- Modify: `frontend/src/modules/collection/components/CreateCollectionJobDialog.vue`
- Modify: `frontend/src/modules/collection/components/ReviewAssetDrawer.vue`
- Modify: `frontend/src/styles/collection.css`
- Test: `frontend/src/modules/collection/collectionViews.spec.ts`

**Interfaces:**
- Consumes: Task 1 primitives and Task 3 collection shell; no API or workspace signature changes.
- Produces: one continuous three-stage acquisition rail, compact metrics, prioritized current-task state, table-first asset management, spatially clear dialogs/drawer, and explicit research handoff.

- [ ] **Step 1: Write failing collection presentation checks**

Add focused raw-component assertions for the continuous stage status, readable “查看原文” action, immutable original-review presentation, explicit “不自动调用大模型” handoff copy, and retained delete confirmation/focus restoration. Extend the design contract for the new stage, metric and drawer classes.

- [ ] **Step 2: Run the focused checks and verify RED**

Run: `npm.cmd test -- --run src/modules/collection/collectionViews.spec.ts`

Expected: FAIL on the new stage/handoff presentation contract.

Run: `npm.cmd run check:design`

Expected: FAIL on missing new collection surface classes.

- [ ] **Step 3: Implement collection presentation**

Simplify the stage bar and acquire summary, prioritize the active task or start state, consolidate asset filters/table actions, refine the original-review drawer and collection-job dialog motion hooks, and clarify research handoff. Do not add original text editing, bulk delete or automatic LLM execution.

- [ ] **Step 4: Verify GREEN**

Run: `npm.cmd test -- --run src/modules/collection/collectionViews.spec.ts`

Expected: focused tests pass.

Run: `npm.cmd run check:design`

Expected: `Design contract passed.`

- [ ] **Step 5: Commit**

```powershell
git add frontend/scripts/check-design-contract.mjs frontend/src/modules/collection/components/GuidedStageBar.vue frontend/src/modules/collection/components/CreateCollectionJobDialog.vue frontend/src/modules/collection/components/ReviewAssetDrawer.vue frontend/src/modules/collection/views/AcquireView.vue frontend/src/modules/collection/views/AssetsView.vue frontend/src/modules/collection/views/ResearchHandoffView.vue frontend/src/modules/collection/collectionViews.spec.ts frontend/src/styles/collection.css
git commit -m "feat(collection): clarify guided research data workflow"
```

### Task 5: MCDM research surfaces and chart typography

**Files:**
- Modify: `frontend/scripts/check-design-contract.mjs`
- Modify: `frontend/src/components/BaseChart.vue`
- Modify: `frontend/src/modules/mcdm/views/OverviewView.vue`
- Modify: `frontend/src/modules/mcdm/views/DataView.vue`
- Modify: `frontend/src/modules/mcdm/views/CriteriaView.vue`
- Modify: `frontend/src/modules/mcdm/views/ReviewAnalysisView.vue`
- Modify: `frontend/src/modules/mcdm/views/ScenarioView.vue`
- Modify: `frontend/src/modules/mcdm/views/SharesView.vue`
- Modify: `frontend/src/modules/mcdm/views/ExperimentsView.vue`
- Modify: `frontend/src/styles/pages.css`

**Interfaces:**
- Consumes: Task 1 typography/tokens and Task 3 MCDM shell; existing ECharts option and workspace contracts stay unchanged.
- Produces: consistent research-document surfaces, readable dense controls/data, source-adjacent evidence notes and sans-serif chart data typography with animations still disabled.

- [ ] **Step 1: Write the failing MCDM design contract**

Update expectations so `BaseChart.vue` retains `animation: false`, ARIA and resize disposal while using the approved UI sans-serif chain for chart data. Require the overview, data, criteria, review-analysis, scenario, shares and experiments workspaces to expose the approved document/tool-area classes and nearby provenance/status surfaces.

- [ ] **Step 2: Run the design contract and verify RED**

Run: `npm.cmd run check:design`

Expected: FAIL on chart typography and new MCDM surface expectations.

- [ ] **Step 3: Implement MCDM presentation**

Apply the approved hierarchy to all seven pages, remove redundant perimeter borders, tighten tool areas, retain visible data sources/limitations, and update ECharts text families without changing series data, colors that encode research meaning, labels, calculations or animation-disabled behavior.

- [ ] **Step 4: Verify GREEN and frontend regression suite**

Run: `npm.cmd run check:design`

Expected: `Design contract passed.`

Run: `npm.cmd test -- --run`

Expected: all frontend tests pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/scripts/check-design-contract.mjs frontend/src/components/BaseChart.vue frontend/src/modules/mcdm/views frontend/src/styles/pages.css
git commit -m "feat(mcdm): refine research evidence workspace"
```

### Task 6: Documentation, full gates, and rendered browser acceptance

**Files:**
- Modify: `.agents/skills/SOURCES.md`
- Modify: `docs/Skill使用清单.md`
- Create: `docs/研究仪器型UI验收记录.md`
- Verify only: all frontend files changed by Tasks 1–5

**Interfaces:**
- Consumes: completed UI and installed `$emil-design-eng` Skill.
- Produces: auditable Skill provenance, recorded validation results, desktop/tablet/mobile screenshots and final branch evidence.

- [ ] **Step 1: Validate the installed Skill and documentation diff**

Run: `E:/anaconda927/envs/py311/python.exe E:/aaaxz/codexhome/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/emil-design-eng`

Expected: `Skill is valid!`

Run: `git diff --check`

Expected: no output.

- [ ] **Step 2: Run the complete frontend gates**

Run: `npm.cmd test -- --run`

Expected: all frontend tests pass.

Run: `npm.cmd run check:design`

Expected: `Design contract passed.`

Run: `npm.cmd run format:check`

Expected: Prettier reports all matched files use its style.

Run: `npm.cmd run typecheck`

Expected: exit code 0.

Run: `npm.cmd run build`

Expected: production build succeeds; report any existing bundle-size warning without hiding it.

- [ ] **Step 3: Run real-browser acceptance**

Use Playwright CLI against the feature-worktree server for `/`, `/collection`, `/mcdm`, and `/adaptive` at `1440×900`, `1024×768`, and `390×844`. Exercise the mobile drawer, collection dialog, original-review drawer when fixture data permits, and MCDM new-project dialog. Verify `document.documentElement.scrollWidth === window.innerWidth` outside intentional table scrollers. Check a long project/series label, empty/error/planned/read-only states, `prefers-reduced-motion`, 200% zoom, focus restoration, four-digit counts and a long Chinese review without clipping the primary actions. Capture screenshots under `output/playwright/`.

Expected: no new console errors, all routes render, dialogs/drawers open and close, focus returns, and the page itself has no horizontal overflow.

- [ ] **Step 4: Record acceptance evidence**

Create `docs/研究仪器型UI验收记录.md` with actual command outputs, viewport results, screenshot paths, unchanged business boundaries, and any known limitations. Do not claim checks that were not run.

- [ ] **Step 5: Commit**

```powershell
git add .agents/skills/emil-design-eng .agents/skills/SOURCES.md docs/Skill使用清单.md docs/superpowers/specs/2026-10-15-research-instrument-ui-design.md docs/superpowers/plans/2026-10-15-research-instrument-ui.md docs/研究仪器型UI验收记录.md
git commit -m "docs(frontend): record research instrument UI acceptance"
```
