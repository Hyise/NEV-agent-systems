# Series Catalog Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a two-stage workflow that first discovers and atomically publishes up to 1000 unique Autohome series, then creates review-collection jobs from an explicit user selection.

**Architecture:** Add a catalog domain, repository, background service, and API beside the existing review collection modules, with a shared external-access coordinator preventing catalog discovery and review collection from running together. Store catalog batches and new job manifests in normalized SQLite tables, preserve the legacy JSON manifest only for old jobs, and move the frontend creation flow into a focused catalog-selection state module and dialog component.

**Tech Stack:** Python 3.9+, FastAPI, Pydantic v2, SQLite, Playwright, httpx, Vue 3 Composition API, TypeScript, Vitest, Vite.

**Spec:** `docs/superpowers/specs/2026-10-09-series-catalog-selection-design.md`

## Global Constraints

- “前 1000 个车型” means the first 1000 unique `platform + series_id` values in discovery order; year, facelift, and configuration variants do not count separately.
- Every catalog entry must contain both a numeric `series_id` and a non-empty `series_name`.
- Verification jobs select 1–3 series and collect at most 2 pages per series; production jobs select 1–1000 series and have no page cap.
- A new job must use an immutable normalized snapshot of the active catalog; later catalog refreshes cannot change it.
- Catalog discovery and review collection must never access Autohome concurrently, while cached reads and exports remain available.
- A refresh must not clear the current catalog before successful publication; failure or cancellation keeps the previous catalog active.
- New catalog access remains restricted to the existing Autohome HTTPS allowlist and does not bypass `403`, `429`, or verification pages.
- Existing jobs, reviews, exports, and full review-detail content remain readable; new jobs do not write `collection_jobs.series_manifest`.
- No Redis, Celery, distributed workers, automatic scheduled refresh, advanced brand/price filters, or full 1000-series production crawl is added.
- UI copy and layout continue the current restrained Chinese research-workbench design and the project-wide SimSun font fallback.

## Review Focus

- A user submits IDs from a catalog batch that was replaced after the page loaded: the API returns `422` with the invalid IDs and creates no job (Task 5 test).
- A request contains duplicate series IDs: validation rejects it instead of silently altering order or count (Task 5 test).
- Catalog publication fails after entries were staged: the former `active_batch_id` and its visible entries remain unchanged (Task 1 test).
- Cancellation arrives while a source request is in flight: it takes effect before the next request/scroll and never publishes the staged batch (Task 3 test).
- A catalog run and review job race to start, or executor submission fails: exactly one reservation wins and every failed start releases its reservation (Tasks 3 and 5 tests).

---

### Task 1: Persist versioned catalog batches atomically

**Files:**
- Create: `backend/collection/catalog_domain.py`
- Create: `backend/collection/catalog_repository.py`
- Create: `backend/tests/test_series_catalog_repository.py`
- Modify: `backend/collection/repository.py:31-110`
- Modify: `backend/tests/test_collection_repository.py:56-108`

**Interfaces:**
- Produces: `CatalogRunStatus`, `CatalogRunConflict`, and `CatalogSelectionError` from `catalog_domain.py`.
- Produces: `SeriesCatalogRepository(path: Path)` with `create_run`, `get_run`, `active_run`, `append_entries`, `request_cancel`, `is_cancel_requested`, `publish_run`, `fail_run`, `cancel_run`, `catalog_status`, `list_catalog`, `selection_ids`, and `fail_interrupted_runs`.
- Produces: SQLite tables `series_catalog_runs`, `series_catalog_entries`, `series_catalog_state`, and `collection_job_series`.
- Consumes: existing `VehicleSeries` validation from `backend.collection.domain`.

- [ ] **Step 1: Write failing schema and batch-isolation tests**

Add tests named `test_catalog_repository_creates_versioned_tables`, `test_append_entries_deduplicates_within_batch_and_preserves_first_rank`, and `test_unpublished_batch_is_not_visible` in `backend/tests/test_series_catalog_repository.py`. Assert all four new tables exist, duplicate `series_id` values remain one row with their first rank, and `list_catalog()` stays empty before publication.

- [ ] **Step 2: Run the new repository tests and verify the missing module failure**

Run: `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_series_catalog_repository.py -q`

Expected: FAIL because `backend.collection.catalog_repository` and `catalog_domain` do not exist.

- [ ] **Step 3: Define catalog states and create the catalog repository schema**

Implement `CatalogRunStatus(StrEnum)` with `queued`, `discovering`, `publishing`, `completed`, `completed_short`, `cancelling`, `cancelled`, and `failed`. Implement the repository constructor so repeated startup is idempotent and `series_catalog_state` has one row whose `active_batch_id` may be null.

- [ ] **Step 4: Implement staged entry insertion and current-catalog reads**

Implement:

```python
def append_entries(self, run_id: str, entries: list[VehicleSeries], *, scanned_count: int, skipped_count: int, current_page: int, updated_at: str) -> dict[str, Any]
def list_catalog(self, query: str = "", page: int = 1, page_size: int = 20) -> dict[str, Any]
def selection_ids(self, query: str = "") -> list[str]
```

`append_entries` uses the run's `batch_id`, inserts only unseen IDs, and never mutates an earlier rank. Read methods join only the active batch and use the same case-insensitive name/ID containment rule.

- [ ] **Step 5: Run the isolation tests and verify they pass**

Run: `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_series_catalog_repository.py -q`

Expected: PASS for the schema, deduplication, and unpublished-read tests.

- [ ] **Step 6: Write failing atomic publication and restart tests**

Add `test_publish_switches_active_batch_in_one_transaction`, `test_publish_failure_keeps_previous_batch_active`, `test_failed_and_cancelled_runs_discard_staged_entries`, `test_only_three_unreferenced_successful_batches_are_retained`, and `test_restart_fails_interrupted_run_without_changing_active_catalog`. Inject a failing connection/statement for the publication rollback assertion rather than simulating success.

- [ ] **Step 7: Implement the run lifecycle and atomic publication**

Implement:

```python
def create_run(self, run_id: str, batch_id: str, created_at: str, target_unique_series: int = 1000) -> dict[str, Any]
def get_run(self, run_id: str) -> dict[str, Any] | None
def active_run(self) -> dict[str, Any] | None
def request_cancel(self, run_id: str, updated_at: str) -> dict[str, Any]
def is_cancel_requested(self, run_id: str) -> bool
def publish_run(self, run_id: str, published_at: str, source_exhausted: bool) -> dict[str, Any]
def fail_run(self, run_id: str, error_code: str, error_message: str, finished_at: str) -> dict[str, Any]
def cancel_run(self, run_id: str, finished_at: str) -> dict[str, Any]
def catalog_status(self) -> dict[str, Any]
def fail_interrupted_runs(self, failed_at: str) -> int
```

`publish_run` changes the run to `publishing`, updates `active_batch_id`, summary count, `published_at`, and terminal status in one transaction. Use `completed_short` only when `source_exhausted=True` and fewer than 1000 entries exist. Cleanup retains the newest three successful batches and any older batch referenced by `collection_job_series`.

- [ ] **Step 8: Add the normalized job-series table without changing current job behavior**

Extend `CollectionRepository.__init__` to create `collection_job_series` with the fields and uniqueness from the spec. Do not yet change `create_job` or service execution; this step is a non-destructive migration only. Update the existing schema-count test to assert the original tables plus the normalized manifest table.

- [ ] **Step 9: Run repository regression tests**

Run: `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_series_catalog_repository.py backend/tests/test_collection_repository.py -q`

Expected: PASS.

- [ ] **Step 10: Commit the persistence layer**

```bash
git add backend/collection/catalog_domain.py backend/collection/catalog_repository.py backend/collection/repository.py backend/tests/test_series_catalog_repository.py backend/tests/test_collection_repository.py
git commit -m "feat(collection): persist versioned series catalogs"
```

### Task 2: Make Autohome discovery progressive and cancellable

**Files:**
- Modify: `backend/collection/autohome.py:49-64,190-213,272-394`
- Modify: `backend/tests/test_autohome_adapter.py:61-145`

**Interfaces:**
- Consumes: `VehicleSeries` and the existing Autohome host/request guard.
- Produces: `CatalogDiscoveryCancelled(AutohomeSourceError)`.
- Produces: `CatalogDiscoveryResult.series`, `.session`, `.scanned_count`, `.skipped_count`, and `.source_exhausted`.
- Produces: `AutohomeCatalogAdapter.discover_series(max_series: int, on_batch: Callable[[list[VehicleSeries], int, int, int], None] | None = None, should_cancel: Callable[[], bool] | None = None) -> CatalogDiscoveryResult`.
- Preserves: `discover(max_series)` as the legacy wrapper needed to resume pre-upgrade jobs.

- [ ] **Step 1: Write failing progressive discovery tests**

Add `test_discovery_reports_new_unique_series_in_first_seen_order`, `test_discovery_scans_past_duplicates_until_1000_unique_series`, and `test_discovery_marks_normal_source_exhaustion`. Use the existing fake Playwright page pattern; assert callback batches contain only newly discovered series and ranks remain globally monotonic.

- [ ] **Step 2: Run the focused adapter tests and verify failure**

Run: `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_autohome_adapter.py -q`

Expected: FAIL because `discover_series` and the extended result fields are absent.

- [ ] **Step 3: Implement progressive extraction without weakening source validation**

Keep the scoped selector and URL guards. Track first-seen raw candidates by normalized `(href, name)` so links already present during a later scroll round are not counted again. Increment `scanned_count` for each first-seen candidate and `skipped_count` when that candidate lacks a numeric ID or name, deduplicate valid results globally by `series_id`, and call `on_batch(new_entries, scanned_count, skipped_count, load_round)` after each DOM read that yields new entries.

- [ ] **Step 4: Write failing cancellation and structural-drift tests**

Add `test_discovery_cancels_before_the_next_scroll`, `test_nonempty_round_with_zero_valid_entries_fails`, and `test_required_field_failure_rate_over_five_percent_after_one_hundred_items_fails`. Assert cancellation raises `CatalogDiscoveryCancelled` and no further page operation occurs.

- [ ] **Step 5: Implement cancellation and the exact validity thresholds**

Check `should_cancel()` after navigation and before every later scroll/read. Raise `AutohomeStructureError` when a non-empty candidate set produces zero valid entries, or after at least 100 candidates when more than 5% lack required fields. Five unchanged scroll rounds set `source_exhausted=True`; reaching 1000 sets it to `False`.

- [ ] **Step 6: Preserve legacy discovery and session establishment**

Make `discover(max_series)` delegate to `discover_series(max_series)` and keep returning the browser session expected by legacy collection jobs. Keep `open_session()` unchanged for selected-series jobs.

- [ ] **Step 7: Run all adapter tests**

Run: `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_autohome_adapter.py -q`

Expected: PASS, including full-review detail tests.

- [ ] **Step 8: Commit the adapter increment**

```bash
git add backend/collection/autohome.py backend/tests/test_autohome_adapter.py
git commit -m "feat(collection): stream cancellable series discovery"
```

### Task 3: Run catalog discovery in the background with shared reservation semantics

**Files:**
- Create: `backend/collection/coordination.py`
- Create: `backend/collection/catalog_service.py`
- Create: `backend/tests/test_series_catalog_service.py`

**Interfaces:**
- Consumes: `SeriesCatalogRepository` from Task 1 and `AutohomeCatalogAdapter.discover_series` from Task 2.
- Produces: `ExternalAccessCoordinator.try_reserve(kind: Literal["catalog", "collection"], operation_id: str) -> bool`, `release(kind, operation_id) -> None`, and `current() -> ExternalAccessReservation | None`.
- Produces: `SeriesCatalogService.start(run_id: str, batch_id: str) -> Future[None]`, `cancel(run_id: str) -> None`, `run_discovery(run_id: str) -> None`, and `shutdown() -> None`; the service clock supplies `created_at`.

- [ ] **Step 1: Write failing coordinator race tests**

Add `test_exactly_one_external_operation_wins_a_start_race`, `test_only_the_owner_can_release_a_reservation`, and `test_failed_executor_submission_releases_reservation`. Use barriers/events rather than sleeps.

- [ ] **Step 2: Run the service tests and verify missing-module failure**

Run: `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_series_catalog_service.py -q`

Expected: FAIL because `coordination.py` and `catalog_service.py` do not exist.

- [ ] **Step 3: Implement the thread-safe external-access coordinator**

Use one internal `threading.Lock` protecting an optional immutable reservation. A failed `try_reserve` returns `False` without queueing; a mismatched release raises a control error so one task cannot release another task's lease.

- [ ] **Step 4: Write failing catalog lifecycle tests**

Add `test_discovery_stages_progress_and_publishes_1000_unique_series`, `test_exhausted_source_completes_short`, `test_source_failure_keeps_old_catalog`, `test_cancel_during_request_stops_before_next_batch_and_does_not_publish`, and `test_shutdown_marks_running_catalog_interrupted`. Assert the coordinator is free after every terminal path.

- [ ] **Step 5: Implement `SeriesCatalogService` lifecycle**

`start` reserves external access before creating and submitting a target-1000 run. Any run-creation or executor-submission failure marks an already-created run `failed` where applicable and releases the reservation. `run_discovery` passes repository staging and cancellation callbacks to the adapter, publishes only after successful completion, sanitizes adapter exceptions into catalog-run errors, and releases in `finally`.

- [ ] **Step 6: Implement cooperative cancellation and shutdown**

`cancel` moves an active run to `cancelling`; the adapter callback observes repository state before the next source operation. `shutdown` requests cancellation, waits for the single executor, and leaves no non-terminal run or reservation behind.

- [ ] **Step 7: Run catalog repository and service tests together**

Run: `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_series_catalog_repository.py backend/tests/test_series_catalog_service.py -q`

Expected: PASS.

- [ ] **Step 8: Commit background discovery**

```bash
git add backend/collection/coordination.py backend/collection/catalog_service.py backend/tests/test_series_catalog_service.py
git commit -m "feat(collection): add background catalog discovery"
```

### Task 4: Expose catalog discovery and selection APIs

**Files:**
- Create: `backend/collection/catalog_api.py`
- Modify: `backend/app.py:33-55,105`
- Modify: `backend/tests/test_collection_api.py:1-110`
- Create: `backend/tests/test_series_catalog_api.py`

**Interfaces:**
- Consumes: catalog service/repository and coordinator from Tasks 1 and 3.
- Produces: `create_catalog_router(repository: SeriesCatalogRepository, service: SeriesCatalogService) -> APIRouter`.
- Produces: `GET /api/collection/catalog`, `GET /catalog/selection`, `GET /catalog/status`, `POST /catalog/discover`, `GET /catalog/discover/{run_id}`, and `POST /catalog/discover/{run_id}/cancel`.
- Extends: `create_app(..., collection_service_factory=None, catalog_service_factory=None)` while preserving existing collection-test injection.

- [ ] **Step 1: Write failing catalog API contract tests**

Add tests for empty status, discovery start `202`, second active run `409`, paginated query, selection IDs using the identical query, run detail `404`, cancel, and `completed_short` serialization. Assert list rows contain `batch_id` and `published_at`.

- [ ] **Step 2: Run the API tests and verify missing-route failures**

Run: `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_series_catalog_api.py -q`

Expected: FAIL with route-not-found responses.

- [ ] **Step 3: Implement the catalog router**

Keep the router thin: validate `page >= 1`, `1 <= page_size <= 100`, and string query length; map missing runs to `404`, active/reservation conflicts to `409`, and invalid requests to `422`. `POST /catalog/discover` creates UUID values for `run_id` and `batch_id` through the service contract and returns the persisted run.

- [ ] **Step 4: Wire shared production dependencies and lifecycle cleanup**

In `create_app`, construct `CollectionRepository` first so its normalized manifest table exists before catalog cleanup, then construct one `ExternalAccessCoordinator`, `SeriesCatalogRepository`, and `SeriesCatalogService`. Mount both routers, expose dependencies on `app.state`, call `pause_interrupted_jobs` and `fail_interrupted_runs` at startup, and call both `shutdown()` methods at exit. Preserve the old one-argument `collection_service_factory(repository)` test hook; Task 5 injects the shared coordinator into the default collection service after that service gains the interface.

- [ ] **Step 5: Update API fixtures for the second service without hiding shutdown failures**

Add a recording catalog service factory that exposes `start`, `cancel`, and `shutdown`. Assert both injected services are shut down by the FastAPI lifespan.

- [ ] **Step 6: Run catalog and existing collection API tests**

Run: `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_series_catalog_api.py backend/tests/test_collection_api.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the catalog HTTP boundary**

```bash
git add backend/collection/catalog_api.py backend/app.py backend/tests/test_series_catalog_api.py backend/tests/test_collection_api.py
git commit -m "feat(collection): expose series catalog API"
```

### Task 5: Create collection jobs from immutable selected-series snapshots

**Files:**
- Modify: `backend/collection/domain.py:10-70`
- Modify: `backend/collection/repository.py:126-205,311-355`
- Modify: `backend/collection/service.py:29-159,267-460`
- Modify: `backend/collection/api.py:32-75`
- Modify: `backend/collection/coordination.py`
- Modify: `backend/app.py:33-55,105`
- Modify: `backend/tests/test_collection_domain.py:15-64`
- Modify: `backend/tests/test_collection_repository.py`
- Modify: `backend/tests/test_collection_service.py:93-165,619-720`
- Modify: `backend/tests/test_collection_api.py:113-154`

**Interfaces:**
- Consumes: active catalog tables from Task 1 and shared coordinator from Task 3.
- Produces: `CreateJobBody.selected_series_ids: list[str]` with numeric, unique, mode-specific validation.
- Produces: `CollectionRepository.create_job_from_catalog(job_id: str, config: JobConfig, selected_series_ids: list[str], created_at: str) -> dict[str, Any]`.
- Produces: `CollectionRepository.job_series(job_id: str) -> list[VehicleSeries]`, normalized first with legacy JSON fallback.
- Changes: new selected-series jobs transition `queued → collecting`; `discovering` remains only for legacy jobs.

- [ ] **Step 1: Write failing request-validation tests**

Replace the old “production fixed to 500” assertions with tests named `test_verification_requires_one_to_three_unique_numeric_series_ids`, `test_production_requires_one_to_one_thousand_unique_numeric_series_ids`, and `test_duplicate_series_ids_are_rejected_without_reordering`. Assert verification derives `max_series` from selection and fixes two pages; production derives count and sets no cap.

- [ ] **Step 2: Run domain tests and verify the old contract fails**

Run: `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_collection_domain.py -q`

Expected: FAIL until `CreateJobBody` and `JobConfig.max_series <= 1000` are updated.

- [ ] **Step 3: Implement the selected-series domain contract**

Remove client-controlled `max_series` and `max_pages_per_series` from new request semantics. Validate the exact selected-ID bounds, preserve submitted order, and keep all approved delay minimums and ordering checks unchanged.

- [ ] **Step 4: Write failing transactional snapshot tests**

Add `test_create_job_snapshots_selected_active_catalog_in_submitted_order`, `test_stale_batch_ids_return_all_invalid_ids_and_create_no_job`, `test_empty_or_duplicate_selection_creates_no_job`, and `test_legacy_json_manifest_remains_readable`. Change the catalog between browse and submit in the stale-batch test.

- [ ] **Step 5: Implement atomic catalog-to-job snapshot creation**

In one `BEGIN IMMEDIATE` transaction, read the current active batch, resolve every submitted ID, reject missing IDs with `CatalogSelectionError.invalid_series_ids`, insert `collection_jobs`, and insert ordered `collection_job_series` rows. Set `discovered_count` to the selected count. Leave `series_manifest` as `'[]'` for new jobs; `job_series()` falls back to the JSON column only when normalized rows are absent.

- [ ] **Step 6: Write failing service tests for direct collection and mutual exclusion**

Add `test_selected_job_skips_catalog_discovery_and_opens_review_session`, `test_catalog_reservation_blocks_collection_start`, `test_collection_reservation_blocks_catalog_start`, and `test_collection_submit_failure_releases_reservation`. Keep a legacy-job test proving a paused pre-upgrade discovery can still resume.

- [ ] **Step 7: Update `CollectionService` to consume snapshots**

For normalized manifests, reserve `kind="collection"` before executor submission, transition `queued` directly to `collecting`, call `open_session()`, and pass `repository.job_series(job_id)` to `_collect`. Release the reservation on completion, pause, stop, shutdown, and submission failure. Retain the old `discover()` path only when a legacy job has no normalized rows and is queued/discovering.

- [ ] **Step 8: Write failing API selection tests**

Update creation tests to seed an active catalog and submit `selected_series_ids`. Add assertions for empty/too-large/duplicate selections, stale IDs returning `422` with `invalid_series_ids`, no catalog returning `409`, and an active catalog discovery or collection job returning `409`.

- [ ] **Step 9: Update the job endpoint and error mapping**

Pass the catalog repository/coordinator dependency into `create_collection_router` and update `create_app` to inject the shared coordinator into the default `CollectionService`. Call `create_job_from_catalog`; return an object-shaped `detail` with `message` and `invalid_series_ids` for stale selections. Preserve scheduler rollback and `503` behavior without leaving a queued job or held reservation.

- [ ] **Step 10: Run all backend collection tests**

Run: `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests/test_collection_domain.py backend/tests/test_collection_repository.py backend/tests/test_collection_service.py backend/tests/test_collection_api.py backend/tests/test_series_catalog_repository.py backend/tests/test_series_catalog_service.py backend/tests/test_series_catalog_api.py backend/tests/test_autohome_adapter.py -q`

Expected: PASS.

- [ ] **Step 11: Commit selected-series collection**

```bash
git add backend/app.py backend/collection backend/tests/test_collection_domain.py backend/tests/test_collection_repository.py backend/tests/test_collection_service.py backend/tests/test_collection_api.py
git commit -m "feat(collection): collect selected catalog series"
```

### Task 6: Add a focused frontend catalog-selection state module

**Files:**
- Modify: `frontend/src/modules/collection/api.ts`
- Create: `frontend/src/modules/collection/catalogFlow.ts`
- Create: `frontend/src/modules/collection/catalogFlow.spec.ts`
- Modify: `frontend/src/modules/collection/workspace.ts:1-340`
- Modify: `frontend/src/modules/collection/workspace.spec.ts:1-270`

**Interfaces:**
- Produces API types: `CatalogRunStatus`, `CatalogRun`, `CatalogStatus`, `CatalogSeriesRow`, and `CatalogSelectionResult`.
- Extends `CollectionApi` with `getCatalogStatus`, `listCatalog`, `listCatalogSelection`, `startCatalogDiscovery`, `getCatalogRun`, and `cancelCatalogDiscovery`.
- Changes `CreateJobInput` to `{ mode, selected_series_ids, optional delay fields }`.
- Produces `createCatalogFlow(client: CollectionApi, onJobCreated: () => Promise<void>, registerLifecycle?: boolean)` with `open`, `close`, `startDiscovery`, `cancelDiscovery`, `goToSelection`, `loadCatalog`, `search`, `toggleSeries`, `selectFiltered`, `clearSelection`, `createJob`, and `confirmProduction`.

- [ ] **Step 1: Write failing API and state-shape tests**

Create `catalogFlow.spec.ts` with typed mock responses and tests `loads_cached_catalog_status_on_open`, `polls_only_while_discovery_is_non_terminal`, and `closes_without_leaking_poll_timers`. Assert all catalog API paths use encoded queries and the shared `/api/collection` request helper.

- [ ] **Step 2: Run the focused frontend test and verify missing-module failure**

Run: `E:\aaaxz\nodejs0324\npm.cmd test -- --run src/modules/collection/catalogFlow.spec.ts`

Workdir: `frontend`

Expected: FAIL because `catalogFlow.ts` and API methods are absent.

- [ ] **Step 3: Add frontend catalog types and API methods**

Parse string, validation-array, and object-shaped FastAPI `detail` values so stale-selection messages remain readable. `listCatalogSelection(query)` returns IDs for the active batch; it must not infer the set from the visible page.

- [ ] **Step 4: Implement discovery lifecycle and stale-response protection**

Use the same request-token pattern as `workspace.ts`. Poll every 2 seconds only while the dialog is open and the run is `queued`, `discovering`, `publishing`, or `cancelling`. On terminal completion, reload status and the first catalog page.

- [ ] **Step 5: Write failing selection and submission tests**

Add `select_filtered_uses_all_server_matched_ids`, `verification_blocks_more_than_three_without_discarding_selection`, `production_requires_second_confirmation_with_exact_selected_count`, `catalog_version_change_removes_invalid_unsubmitted_ids`, and `successful_job_creation_closes_and_refreshes_workspace`.

- [ ] **Step 6: Implement selection and job submission state**

Keep selection as an ordered `ref<string[]>`, derive the visible checked state, and preserve selections across pagination. Start with no selection. `createJob` submits only `mode` and `selected_series_ids`; validation mode blocks count >3, while production accepts up to 1000 and requires the existing second confirmation pattern.

- [ ] **Step 7: Remove creation responsibilities from the general workspace**

Delete `showCreate`, `jobMode`, production confirmation, and `createJob` from `workspace.ts`; keep job polling, history, series assets, reviews, and task controls unchanged. Update `workspace.spec.ts` by moving only the creation-flow test cases to `catalogFlow.spec.ts`.

- [ ] **Step 8: Run frontend state tests**

Run: `E:\aaaxz\nodejs0324\npm.cmd test -- --run src/modules/collection/catalogFlow.spec.ts src/modules/collection/workspace.spec.ts`

Workdir: `frontend`

Expected: PASS.

- [ ] **Step 9: Commit frontend state separation**

```bash
git add frontend/src/modules/collection/api.ts frontend/src/modules/collection/catalogFlow.ts frontend/src/modules/collection/catalogFlow.spec.ts frontend/src/modules/collection/workspace.ts frontend/src/modules/collection/workspace.spec.ts
git commit -m "feat(frontend): add series catalog selection state"
```

### Task 7: Build the two-step discovery and selection interface

**Files:**
- Create: `frontend/src/modules/collection/components/CreateCollectionJobDialog.vue`
- Modify: `frontend/src/modules/collection/CollectionWorkbench.vue`
- Modify: `frontend/src/modules/collection/views/JobsView.vue`
- Modify: `frontend/src/styles/collection.css`
- Modify: `frontend/scripts/check-design-contract.mjs` only if a stable new structural rule belongs in the design gate

**Interfaces:**
- Consumes: `CatalogFlow` from Task 6 and `CollectionWorkspace.loadWorkspace()`.
- Produces: accessible two-step dialog with discovery status/progress, cached catalog metadata, server-side search, paginated selectable rows, filtered select-all, selection count, mode validation, and production confirmation.
- Preserves: existing job history, control actions, raw-review views, main navigation, and focus restoration.

- [ ] **Step 1: Replace the inline mode-only dialog with the focused component shell**

Move dialog ownership and focus restoration into `CreateCollectionJobDialog.vue`. `CollectionWorkbench.vue` creates one catalog flow, passes `workspace.loadWorkspace` as the success callback, and only opens/closes the component. Keep the existing `dialog`, `cancel`, Escape, and trigger-focus behavior.

- [ ] **Step 2: Implement step one, “发现车系”**

Render current count as `N / 1000`, published time, source exhaustion text, active progress (`current_page`, `scanned_count`, `unique_count`, `skipped_count`), start/restart, cancel, failure text, and the “选择车系并采集” action. During refresh, keep the old catalog summary visible with “正在生成新目录”.

- [ ] **Step 3: Implement step two, “选择车系并采集”**

Render a labeled search input, checkbox rows with name/ID/rank/review-entry availability, paging controls, “全选当前筛选结果”, “清空已选”, and exact selection count. Keep zero items selected initially. Disable submit for zero selections, verification counts over 3, unavailable review URLs, or any external operation conflict.

- [ ] **Step 4: Implement confirmation and catalog-version feedback**

The summary states selected count, 2-page versus unlimited rule, and 2–4/5–10 second delays. Production requires a second explicit action. If catalog revalidation removes IDs, show the removed IDs/count in an alert and keep the remaining valid selection.

- [ ] **Step 5: Update job progress wording for snapshot-based tasks**

In `JobsView.vue`, change “等待发现” fallbacks to “等待采集” for new jobs and derive total series from `discovered_count/max_series` without implying that the task is discovering its own catalog. Keep `discovering` label only for visible legacy jobs.

- [ ] **Step 6: Add restrained responsive styles**

Use borders, spacing, typography, and the existing green accent instead of card grids or decorative gradients. At widths below 768px, stack controls, keep checkbox labels at least 44px high, and contain table/list overflow within the dialog. Status meaning must be present in text, not color alone.

- [ ] **Step 7: Run frontend tests, design checks, typecheck, and build**

Run from `frontend`:

```powershell
E:\aaaxz\nodejs0324\npm.cmd test -- --run
E:\aaaxz\nodejs0324\npm.cmd run check:design
E:\aaaxz\nodejs0324\npm.cmd run typecheck
E:\aaaxz\nodejs0324\npm.cmd run format:check
E:\aaaxz\nodejs0324\npm.cmd run build
```

Expected: all commands exit 0.

- [ ] **Step 8: Commit the interface**

```bash
git add frontend/src/modules/collection frontend/src/styles/collection.css frontend/scripts/check-design-contract.mjs
git commit -m "feat(frontend): add two-step collection workflow"
```

### Task 8: Synchronize engineering documents and complete verification

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/运行须知.md`
- Modify: `docs/开发与架构规范.md`
- Modify: `docs/API与数据契约.md`
- Modify: `docs/系统设计与实施路线.md`
- Modify: `docs/评论数据采集系统验收记录.md`
- Create: `docs/ADR/0003-车系目录发现与评论任务解耦.md`
- Modify: `docs/superpowers/specs/2026-10-09-series-catalog-selection-design.md` status line only after acceptance evidence exists

**Interfaces:**
- Consumes: the implemented API names, states, operational behavior, and exact commands from Tasks 1–7.
- Produces: one consistent operator workflow and architecture record; no aspirational endpoint or state may be documented as implemented before verification.

- [ ] **Step 1: Update architecture and contract documentation**

Document the catalog/service/repository boundaries, shared coordinator, normalized task snapshots, all catalog endpoints, object-shaped stale-selection errors, and legacy manifest read-only compatibility. Add ADR 0003 explaining why discovery is no longer part of each comment job.

- [ ] **Step 2: Update operating instructions and README**

Describe: start the integrated site, install Playwright Chromium if missing, run first discovery, interpret `completed_short`, select verification versus production ranges, cancel discovery, and recover after failure. State explicitly that routine validation does not perform a full 1000-series crawl.

- [ ] **Step 3: Run the complete backend suite**

Run: `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests -q --basetemp .pytest-tmp`

Expected: all tests PASS.

- [ ] **Step 4: Run backend static and diff checks**

Run: `E:\anaconda927\envs\py39232\python.exe -m ruff check backend`

Then run: `git diff --check`

Expected: no lint errors and no whitespace errors.

- [ ] **Step 5: Run the complete frontend quality gate**

Run from `frontend`:

```powershell
E:\aaaxz\nodejs0324\npm.cmd test -- --run
E:\aaaxz\nodejs0324\npm.cmd run check:design
E:\aaaxz\nodejs0324\npm.cmd run typecheck
E:\aaaxz\nodejs0324\npm.cmd run format:check
E:\aaaxz\nodejs0324\npm.cmd run build
```

Expected: every command exits 0.

- [ ] **Step 6: Run a bounded real-source smoke test**

Start the integrated site, launch a limited discovery verification that proves real `series_id`, `series_name`, URLs, deduplication, progress, and cancellation, then select 1–3 series and collect at most 2 pages each. Inspect at least one detail whose list text was truncated and verify its stored `original_review.contents[*].content` contains the full detail-page text. Do not launch a full production crawl.

- [ ] **Step 7: Inspect the UI at desktop and narrow widths**

Verify both steps, cached-data visibility during refresh, search, cross-page selection, validation messages, focus restoration, keyboard controls, job progress, and no whole-page horizontal overflow. Save acceptance screenshots under `output/playwright/collection-catalog/`; record their relative paths in `docs/评论数据采集系统验收记录.md`, and do not commit screenshot files or runtime data.

- [ ] **Step 8: Mark the design status implemented only after evidence passes**

Update the design spec status and any acceptance checklist with the exact test/build/smoke evidence. If live access is unavailable, leave live verification explicitly pending instead of claiming completion.

- [ ] **Step 9: Commit documentation and final evidence**

```bash
git add README.md AGENTS.md docs
git commit -m "docs(collection): document selectable series workflow"
```

- [ ] **Step 10: Request whole-branch code review**

Review the branch against `docs/superpowers/specs/2026-10-09-series-catalog-selection-design.md`, with special attention to transaction boundaries, reservation release paths, legacy job compatibility, complete review text, and frontend stale-response handling. Resolve all Critical and Important findings, rerun affected gates, and commit fixes before integration.

