import pytest
from pydantic import ValidationError

from backend.review_analysis.domain import (
    CriterionSnapshot,
    ReviewAnnotationResult,
    ReviewAsset,
    parse_criteria_proposal,
    parse_review_annotation,
    schema_fingerprint,
    stable_month_series_stratified_sample,
    stable_stratified_sample,
)
from backend.review_analysis.text import extract_analysis_text


def test_extract_analysis_text_preserves_sections_and_removes_exact_duplicates():
    review = {
        "feeling_summary": "整车表现均衡",
        "contents": [
            {"structuredname": "满意", "content": "空间宽敞"},
            {"structuredname": "不满意", "content": "车机偶尔卡顿"},
            {"structuredname": "重复", "content": "空间宽敞"},
        ],
    }

    assert extract_analysis_text(review) == (
        "整车表现均衡\n满意：空间宽敞\n不满意：车机偶尔卡顿"
    )


def test_extract_analysis_text_prefers_tabular_full_review_without_rewriting():
    full_text = "最满意：空间宽敞。\n续航：高速续航稳定，保留完整结尾。"

    assert extract_analysis_text(
        {
            "分项评论全文": full_text,
            "feeling_summary": "不应替代完整表格正文",
            "contents": [{"structuredname": "满意", "content": "不应拼接"}],
        }
    ) == full_text


@pytest.mark.parametrize("review", [{}, {"contents": []}, {"feeling_summary": "  "}])
def test_extract_analysis_text_rejects_empty_review(review):
    with pytest.raises(ValueError, match="没有可分析文本"):
        extract_analysis_text(review)


def test_schema_fingerprint_is_deterministic_and_order_sensitive():
    a = CriterionSnapshot(name="空间", labels=["好", "差"])
    b = CriterionSnapshot(name="续航", labels=["长", "短"])

    assert schema_fingerprint([a, b]) == schema_fingerprint([a, b])
    assert schema_fingerprint([a, b]) != schema_fingerprint([b, a])


def test_stable_stratified_sample_is_reproducible_and_balanced():
    rows = [
        ReviewAsset(
            review_id=f"{series}-{index}",
            series_id=series,
            series_name=f"车系{series}",
            content_hash=f"{index:064x}",
            original_review={"feeling_summary": f"评论{series}-{index}"},
        )
        for series in ("1", "2", "3")
        for index in range(4)
    ]

    first = stable_stratified_sample(list(reversed(rows)), 6)
    second = stable_stratified_sample(rows, 6)

    assert [row.review_id for row in first] == [row.review_id for row in second]
    assert {series: sum(row.series_id == series for row in first) for series in ("1", "2", "3")} == {
        "1": 2,
        "2": 2,
        "3": 2,
    }


def test_month_series_sample_balances_months_before_series():
    rows = []
    for month, series_id, count in (
        ("2026-01-01", "1", 5),
        ("2026-01-02", "2", 3),
        ("2026-02-01", "1", 4),
        ("2026-02-02", "3", 4),
    ):
        for index in range(count):
            rows.append(
                ReviewAsset(
                    review_id=f"{month}-{series_id}-{index}",
                    series_id=series_id,
                    series_name=f"车系{series_id}",
                    content_hash=f"{len(rows) + 1:064x}",
                    original_review={"feeling_summary": "评论"},
                    review_date=month,
                )
            )

    selected = stable_month_series_stratified_sample(rows, 8)

    assert len(selected) == 8
    assert [item.review_date[:7] for item in selected].count("2026-01") == 4
    assert [item.review_date[:7] for item in selected].count("2026-02") == 4
    assert {item.series_id for item in selected} == {"1", "2", "3"}


def test_criteria_proposal_is_strict_and_rejects_long_basis():
    proposal = parse_criteria_proposal(
        {
            "criteria": [
                {
                    "name": "空间实用性",
                    "labels": ["宽敞", "局促"],
                    "similar_terms": ["后排空间"],
                    "basis": "覆盖乘坐与储物空间",
                    "evidence": ["后排坐三个人也不挤"],
                }
            ]
        }
    )
    assert proposal.criteria[0].name == "空间实用性"

    invalid = proposal.model_dump()
    invalid["criteria"][0]["basis"] = "过" * 501
    with pytest.raises(ValidationError):
        parse_criteria_proposal(invalid)

    invalid = proposal.model_dump()
    invalid["unexpected"] = True
    with pytest.raises(ValidationError):
        parse_criteria_proposal(invalid)


def test_review_annotation_rejects_unknown_duplicate_and_fabricated_values():
    criteria = [CriterionSnapshot(name="空间", labels=["宽敞", "局促"])]
    text = "后排坐三个人也不挤，但后备箱较小。"
    valid = {
        "annotations": [
            {
                "criterion": "空间",
                "label": "宽敞",
                "evidence": ["后排坐三个人也不挤"],
                "basis": "评价了后排乘坐空间",
            }
        ],
        "unmatched_evidence": ["后备箱较小"],
    }
    assert isinstance(
        parse_review_annotation(valid, criteria=criteria, review_text=text),
        ReviewAnnotationResult,
    )

    cases = []
    unknown_criterion = {**valid, "annotations": [{**valid["annotations"][0], "criterion": "动力"}]}
    cases.append(unknown_criterion)
    unknown_label = {**valid, "annotations": [{**valid["annotations"][0], "label": "一般"}]}
    cases.append(unknown_label)
    cases.append({**valid, "annotations": valid["annotations"] * 2})
    fake_evidence = {**valid, "annotations": [{**valid["annotations"][0], "evidence": ["不存在的原文"]}]}
    cases.append(fake_evidence)
    cases.append({**valid, "unmatched_evidence": ["不存在的原文"]})
    cases.append({**valid, "unexpected": True})
    cases.append({**valid, "annotations": [{**valid["annotations"][0], "basis": "长" * 501}]})

    for payload in cases:
        with pytest.raises((ValueError, ValidationError)):
            parse_review_annotation(payload, criteria=criteria, review_text=text)
