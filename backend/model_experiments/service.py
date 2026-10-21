from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor


class ExperimentCancelled(Exception):
    pass


class ModelExperimentService:
    def __init__(self, repository, engine):
        self.repository = repository
        self.engine = engine
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="model-experiment"
        )
        self._lock = threading.Lock()
        self._future: Future | None = None

    def _run(self, run_id):
        if not self.repository.claim(run_id):
            return
        try:
            run = self.repository.get(run_id)
            snapshot = self.repository.snapshot(run["snapshot_sha256"])

            def progress(value, current_model):
                if self.repository.cancellation_requested(run_id):
                    raise ExperimentCancelled()
                self.repository.progress(run_id, value, current_model)

            result = self.engine.run(snapshot, progress=progress, **run["config"])
            self.repository.finish(run_id, "completed", result.as_dict())
        except ExperimentCancelled:
            self.repository.finish(run_id, "cancelled")
        # The worker boundary must persist every unexpected model failure instead
        # of leaving a run permanently marked as active.
        except Exception as exc:  # noqa: BLE001
            self.repository.finish(
                run_id, "failed", error_message=f"{type(exc).__name__}: {exc}"
            )

    def start(self, run_id):
        with self._lock:
            self._future = self._executor.submit(self._run, run_id)
            return self._future

    def cancel(self, run_id):
        return self.repository.request_cancel(run_id)

    def shutdown(self):
        self._executor.shutdown(wait=True, cancel_futures=False)
