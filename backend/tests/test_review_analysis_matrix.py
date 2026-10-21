from backend.review_analysis.matrix import build_matrix_preview


CRITERIA = [
    {"name": "空间", "labels": ["宽敞", "局促"]},
    {"name": "舒适", "labels": ["舒适", "颠簸"]},
]


def annotation(
    snapshot_id,
    series_id,
    series_name,
    review_date,
    values,
    *,
    status="succeeded",
):
    return {
        "snapshot_id": snapshot_id,
        "series_id": series_id,
        "series_name": series_name,
        "review_date": review_date,
        "status": status,
        "result": {
            "annotations": [
                {"criterion": criterion, "label": label}
                for criterion, label in values.items()
            ]
        },
    }


def test_builds_month_series_probabilities_and_uses_sales_platform_priority():
    rows = [
        annotation(
            "a1",
            "1",
            "车系一",
            "2026-01-05",
            {"空间": "宽敞", "舒适": "舒适"},
        ),
        annotation(
            "a2",
            "1",
            "车系一",
            "2026-01-20",
            {"空间": "局促", "舒适": "舒适"},
        ),
    ]
    sales = [
        {
            "month": "2026-01",
            "review_series_id": "1",
            "platform": "yiche",
            "sales_volume": 9,
        },
        {
            "month": "2026-01",
            "review_series_id": "1",
            "platform": "autohome",
            "sales_volume": 10,
        },
    ]

    preview = build_matrix_preview(CRITERIA, rows, sales)

    assert preview["blockers"] == []
    assert preview["records"] == [
        {
            "month": "2026-01",
            "model": "车系一",
            "series_id": "1",
            "sales": 10.0,
            "pressure": 0.0,
            "share": 1.0,
            "probabilities": {
                "空间": [0.5, 0.5],
                "舒适": [1.0, 0.0],
            },
            "review_count": 2,
            "sales_platform": "autohome",
        }
    ]


def test_deduplicates_retry_snapshots_and_reports_incomplete_groups():
    rows = [
        annotation(
            "same",
            "1",
            "车系一",
            "2026-02-02",
            {"空间": "宽敞", "舒适": "舒适"},
            status="failed",
        ),
        annotation(
            "same",
            "1",
            "车系一",
            "2026-02-02",
            {"空间": "宽敞", "舒适": "舒适"},
            status="cached",
        ),
        annotation(
            "missing-criterion",
            "2",
            "车系二",
            "2026-02-03",
            {"空间": "局促"},
        ),
        annotation(
            "missing-date",
            "3",
            "车系三",
            None,
            {"空间": "宽敞", "舒适": "颠簸"},
        ),
    ]
    sales = [
        {
            "month": "2026-02",
            "review_series_id": "1",
            "platform": "autohome",
            "sales_volume": 20,
        },
        {
            "month": "2026-02",
            "review_series_id": "2",
            "platform": "autohome",
            "sales_volume": 30,
        },
    ]

    preview = build_matrix_preview(CRITERIA, rows, sales)

    assert preview["stats"] == {
        "source_reviews": 3,
        "groups": 2,
        "records": 1,
        "blocked_groups": 1,
        "missing_date_reviews": 1,
    }
    assert preview["records"][0]["review_count"] == 1
    assert preview["blockers"] == [
        {
            "month": "2026-02",
            "series_id": "2",
            "series_name": "车系二",
            "reasons": ["准则“舒适”没有有效判定"],
        }
    ]


def test_reports_missing_sales_without_emitting_a_record():
    rows = [
        annotation(
            "a1",
            "1",
            "车系一",
            "2026-03-01",
            {"空间": "宽敞", "舒适": "舒适"},
        )
    ]

    preview = build_matrix_preview(CRITERIA, rows, [])

    assert preview["records"] == []
    assert preview["blockers"][0]["reasons"] == ["没有匹配到销量"]
