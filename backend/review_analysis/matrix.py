"""Build reproducible model-input previews from review annotations."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from typing import Any
import uuid

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
    missing_date_reviews = sum(not row.get("review_date") for row in unique_rows)
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
    for (month, series_id, series_name), reviews in sorted(groups.items()):
        reasons: list[str] = []
        probabilities: dict[str, list[float]] = {}
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
                reasons.append(f"准则“{name}”没有有效判定")
            else:
                probabilities[name] = [counts[label] / total for label in labels]

        sales_candidates = sales_by_group.get((month, series_id), [])
        sale = sales_candidates[0] if sales_candidates else None
        if sale is None:
            reasons.append("没有匹配到销量")
        elif float(sale["sales_volume"]) <= 0:
            reasons.append("匹配销量必须大于0")
        elif sum(
            candidate["platform"] == sale["platform"]
            for candidate in sales_candidates
        ) > 1:
            reasons.append("最高优先级平台存在重复销量")
        if month < "2026-01":
            reasons.append("2026年前月份缺少时间压力数据")

        if reasons:
            blockers.append(
                {
                    "month": month,
                    "series_id": series_id,
                    "series_name": series_name,
                    "reasons": reasons,
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
        "stats": {
            "source_reviews": len(unique_rows),
            "groups": len(groups),
            "records": len(records),
            "blocked_groups": len(blockers),
            "missing_date_reviews": missing_date_reviews,
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

    def materialize(self, project_id: str, job_id: str) -> dict[str, Any]:
        preview = self.preview(project_id, job_id)
        if preview["blockers"] or preview["stats"]["missing_date_reviews"]:
            raise ValueError("评价矩阵仍有缺失日期、准则判定或销量匹配")
        if not preview["records"]:
            raise ValueError("没有可保存的评价矩阵记录")
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
            schema_id=preview["schema_id"],
            name=f"评论标注矩阵-{job_id[:8]}",
            digest=digest,
            records=records,
            created_at=_now(),
        )
