"""Build reproducible model-input previews from review annotations."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from typing import Any
import uuid

from .domain import CriterionSnapshot, schema_fingerprint
from .repository import _now


PLATFORM_PRIORITY = {"autohome": 0, "dongchedi": 1, "yiche": 2}
SUCCESS_STATUSES = {"succeeded", "cached"}


def _deduplicate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("snapshot_id") or row.get("review_id"))
        current = selected.get(key)
        if current is None or (
            row.get("status") in SUCCESS_STATUSES
            and current.get("status") not in SUCCESS_STATUSES
        ):
            selected[key] = row
    return list(selected.values())


def _sales_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    result: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        series_id = row.get("review_series_id")
        if series_id:
            result[(str(row["month"]), str(series_id))].append(row)
    for values in result.values():
        values.sort(key=lambda row: (PLATFORM_PRIORITY.get(str(row["platform"]), 99), str(row["platform"])))
    return result


def build_matrix_preview(
    criteria: list[dict[str, Any]],
    annotation_rows: list[dict[str, Any]],
    sales_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    unique_rows = _deduplicate(annotation_rows)
    missing_date_items = [
        {
            "asset_id": row.get("source_asset_id"),
            "review_id": str(row.get("review_id") or row.get("snapshot_id") or ""),
            "series_id": str(row.get("series_id") or ""),
            "series_name": str(row.get("series_name") or ""),
        }
        for row in unique_rows
        if not row.get("review_date")
    ]
    missing_date_reviews = len(missing_date_items)
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in unique_rows:
        if row.get("status") not in SUCCESS_STATUSES or not row.get("review_date"):
            continue
        groups[
            (
                str(row["review_date"])[:7],
                str(row["series_id"]),
                str(row["series_name"]),
            )
        ].append(row)

    sales_by_group = _sales_index(sales_rows)
    records: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for (month, series_id, series_name), reviews in sorted(groups.items()):
        issues: list[dict[str, str]] = []
        probabilities: dict[str, list[float]] = {}
        criterion_coverage: dict[str, float] = {}
        unmentioned_criteria: list[str] = []
        for criterion in criteria:
            name = str(criterion["name"])
            labels = [str(label) for label in criterion["labels"]]
            counts: Counter[str] = Counter()
            for review in reviews:
                for item in (review.get("result") or {}).get("annotations", []):
                    if item.get("criterion") == name and item.get("label") in labels:
                        counts[str(item["label"])] += 1
                        break
            total = sum(counts.values())
            if not total:
                probabilities[name] = [1.0 / len(labels)] * len(labels)
                criterion_coverage[name] = 0.0
                unmentioned_criteria.append(name)
            else:
                probabilities[name] = [counts[label] / total for label in labels]
                criterion_coverage[name] = total / len(reviews)

        if unmentioned_criteria:
            quoted = "、".join(f"“{name}”" for name in unmentioned_criteria)
            warnings.append(
                {
                    "month": month,
                    "series_id": series_id,
                    "series_name": series_name,
                    "unmentioned_criteria": unmentioned_criteria,
                    "message": f"准则{quoted}未被本组评论提及，已采用中性均匀分布",
                }
            )

        sales_candidates = sales_by_group.get((month, series_id), [])
        sale = sales_candidates[0] if sales_candidates else None
        if sale is None:
            issues.append({"code": "missing_sales", "message": "没有匹配到销量"})
        elif float(sale["sales_volume"]) <= 0:
            issues.append(
                {"code": "invalid_sales", "message": "匹配销量必须大于0"}
            )
        elif sum(
            candidate["platform"] == sale["platform"]
            for candidate in sales_candidates
        ) > 1:
            issues.append(
                {
                    "code": "duplicate_sales",
                    "message": "最高优先级平台存在重复销量",
                }
            )
        if month < "2026-01":
            issues.append(
                {
                    "code": "historical_pressure",
                    "message": "2026年前月份缺少时间压力数据",
                }
            )

        if issues:
            blockers.append(
                {
                    "month": month,
                    "series_id": series_id,
                    "series_name": series_name,
                    "reasons": [issue["message"] for issue in issues],
                    "issues": issues,
                }
            )
            continue
        records.append(
            {
                "month": month,
                "model": series_name,
                "series_id": series_id,
                "sales": float(sale["sales_volume"]),
                "pressure": 0.0,
                "share": 0.0,
                "probabilities": probabilities,
                "criterion_coverage": criterion_coverage,
                "review_count": len(reviews),
                "sales_platform": str(sale["platform"]),
            }
        )

    monthly_totals: dict[str, float] = defaultdict(float)
    for record in records:
        monthly_totals[record["month"]] += record["sales"]
    for record in records:
        record["share"] = record["sales"] / monthly_totals[record["month"]]

    return {
        "records": records,
        "blockers": blockers,
        "warnings": warnings,
        "missing_date_items": missing_date_items,
        "stats": {
            "source_reviews": len(unique_rows),
            "groups": len(groups),
            "records": len(records),
            "blocked_groups": len(blockers),
            "missing_date_reviews": missing_date_reviews,
            "unmentioned_criterion_groups": len(warnings),
        },
    }


class ReviewMatrixService:
    def __init__(self, repository):
        self.repository = repository

    def preview(self, project_id: str, job_id: str) -> dict[str, Any]:
        context = self.repository.matrix_inputs(project_id, job_id)
        if context is None:
            raise KeyError(job_id)
        job = context["job"]
        if job["job_type"] != "review_annotation":
            raise ValueError("只有逐条评论标注任务可以生成评价矩阵")
        if job["status"] not in {"completed", "partial_failed"}:
            raise ValueError("评论标注任务尚未结束")
        preview = build_matrix_preview(
            job["criteria"], context["annotations"], context["sales"]
        )
        preview["job_id"] = job_id
        preview["project_id"] = project_id
        preview["schema_id"] = job["schema_id"]
        preview["failed_reviews"] = sum(
            row.get("status") not in SUCCESS_STATUSES
            for row in _deduplicate(context["annotations"])
        )
        return preview

    @staticmethod
    def _schema_fingerprint(criteria: list[dict[str, Any]]) -> str:
        return schema_fingerprint(
            [CriterionSnapshot.model_validate(item) for item in criteria]
        )

    def handoff(self, project_id: str, schema_id: str) -> dict[str, Any]:
        schema = self.repository.get_schema(project_id, schema_id)
        if schema is None:
            raise KeyError(schema_id)
        dataset = self.repository.latest_dataset(project_id, schema_id)
        if dataset is not None:
            return {
                "state": "materialized",
                "target_schema_id": schema_id,
                "target_schema_version": schema["version"],
                "target_schema_status": schema["status"],
                "compatibility": "exact",
                "job": None,
                "matrix": None,
                "dataset": dataset,
            }
        candidate = self.repository.latest_annotation_job(
            project_id, schema_id, self._schema_fingerprint(schema["criteria"])
        )
        if candidate is None:
            return {
                "state": "no_job",
                "target_schema_id": schema_id,
                "target_schema_version": schema["version"],
                "target_schema_status": schema["status"],
                "compatibility": None,
                "job": None,
                "matrix": None,
                "dataset": None,
            }
        job, compatibility = candidate
        source_schema = self.repository.get_schema(project_id, job["schema_id"])
        job_summary = {
            "id": job["id"],
            "status": job["status"],
            "source_schema_id": job["schema_id"],
            "source_schema_version": source_schema["version"] if source_schema else None,
        }
        if job["status"] not in {"completed", "partial_failed"}:
            return {
                "state": "processing",
                "target_schema_id": schema_id,
                "target_schema_version": schema["version"],
                "target_schema_status": schema["status"],
                "compatibility": compatibility,
                "job": job_summary,
                "matrix": None,
                "dataset": None,
            }
        preview = self.preview(project_id, job["id"])
        blocker_counts: Counter[str] = Counter(
            issue["code"]
            for blocker in preview["blockers"]
            for issue in blocker["issues"]
        )
        blocked = bool(
            preview["blockers"]
            or preview["stats"]["missing_date_reviews"]
            or preview["failed_reviews"]
        )
        return {
            "state": "blocked" if blocked else "ready",
            "target_schema_id": schema_id,
            "target_schema_version": schema["version"],
            "target_schema_status": schema["status"],
            "compatibility": compatibility,
            "job": job_summary,
            "matrix": {
                "stats": preview["stats"],
                "failed_reviews": preview["failed_reviews"],
                "blocker_counts": dict(blocker_counts),
                "first_blocker": preview["blockers"][0]
                if preview["blockers"]
                else None,
            },
            "dataset": None,
        }

    def materialize(
        self, project_id: str, job_id: str, target_schema_id: str | None = None
    ) -> dict[str, Any]:
        preview = self.preview(project_id, job_id)
        if (
            preview["blockers"]
            or preview["stats"]["missing_date_reviews"]
            or preview["failed_reviews"]
        ):
            raise ValueError("评价矩阵仍有失败评论、缺失日期、销量或历史压力问题")
        if not preview["records"]:
            raise ValueError("没有可保存的评价矩阵记录")
        target_schema_id = target_schema_id or preview["schema_id"]
        target_schema = self.repository.get_schema(project_id, target_schema_id)
        if target_schema is None:
            raise ValueError("目标准则版本不存在")
        if target_schema["status"] != "frozen":
            raise ValueError("目标准则版本尚未冻结")
        if self._schema_fingerprint(target_schema["criteria"]) != self._schema_fingerprint(
            self.repository.get_job(job_id)["criteria"]
        ):
            raise ValueError("目标准则版本与评论任务的准则内容不一致")
        records = preview["records"]
        canonical = json.dumps(
            records,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return self.repository.save_matrix_dataset(
            dataset_id=uuid.uuid4().hex,
            project_id=project_id,
            schema_id=target_schema_id,
            name=f"评论标注矩阵-{job_id[:8]}-V{target_schema['version']}",
            digest=digest,
            records=records,
            created_at=_now(),
            source_job_id=job_id,
            source_schema_id=preview["schema_id"],
        )
