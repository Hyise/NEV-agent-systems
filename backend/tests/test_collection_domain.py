import pytest
from pydantic import ValidationError

from backend.collection.domain import (
    CollectedReview,
    CreateJobBody,
    JobStatus,
    TaskControlError,
    VehicleSeries,
    canonical_review_hash,
    transition_status,
)


def test_verification_defaults_to_three_series_and_two_pages():
    body = CreateJobBody(mode="verification")

    assert body.max_series == 3
    assert body.max_pages_per_series == 2
    assert body.request_delay_min_seconds == 2
    assert body.request_delay_max_seconds == 4
    assert body.series_delay_min_seconds == 5
    assert body.series_delay_max_seconds == 10


def test_production_is_fixed_to_500_series_and_unlimited_pages():
    body = CreateJobBody(mode="production")

    assert body.max_series == 500
    assert body.max_pages_per_series is None
    with pytest.raises(ValidationError):
        CreateJobBody(mode="production", max_series=499)
    with pytest.raises(ValidationError):
        CreateJobBody(mode="production", max_pages_per_series=2)


@pytest.mark.parametrize(
    "values",
    [
        {"request_delay_min_seconds": 0},
        {"series_delay_min_seconds": 0},
        {"request_delay_min_seconds": 4, "request_delay_max_seconds": 2},
        {"series_delay_min_seconds": 10, "series_delay_max_seconds": 5},
    ],
)
def test_delay_cannot_be_zero_or_reverse(values):
    with pytest.raises(ValidationError):
        CreateJobBody(mode="verification", **values)


@pytest.mark.parametrize(
    "values",
    [
        {"request_delay_min_seconds": 1.99},
        {"request_delay_max_seconds": 1.99},
        {"series_delay_min_seconds": 4.99},
        {"series_delay_max_seconds": 4.99},
    ],
)
def test_delay_cannot_be_faster_than_approved_policy(values):
    with pytest.raises(ValidationError):
        CreateJobBody(mode="verification", **values)


def test_only_paused_job_can_resume():
    assert transition_status(JobStatus.PAUSED, "resume") is JobStatus.COLLECTING

    with pytest.raises(TaskControlError):
        transition_status(JobStatus.COLLECTING, "resume")


@pytest.mark.parametrize(
    "values",
    [
        {"series_id": "", "series_name": "Model Y"},
        {"series_id": "5769", "series_name": ""},
        {"series_id": "not-a-number", "series_name": "Model Y"},
    ],
)
def test_series_requires_id_and_name(values):
    with pytest.raises(ValidationError):
        VehicleSeries(
            **values,
            series_url="https://www.autohome.com.cn/5769/",
            review_url="https://k.autohome.com.cn/5769/",
            discovery_rank=1,
        )


def test_canonical_hash_ignores_json_key_order():
    first = {"Koubeiid": "abc", "contents": [{"name": "满意", "content": "安静"}]}
    second = {"contents": [{"content": "安静", "name": "满意"}], "Koubeiid": "abc"}

    assert canonical_review_hash(first) == canonical_review_hash(second)
    assert len(canonical_review_hash(first)) == 64


def test_collected_review_keeps_original_object_intact():
    original = {
        "Koubeiid": "abc",
        "specname": "2025款 长续航版",
        "contents": [{"structuredname": "满意", "content": "空间充足"}],
        "unknown": {"nested": [1, "中文", None]},
    }

    review = CollectedReview(
        platform="autohome",
        review_id="abc",
        series_id="5769",
        series_name="Model Y",
        source_url="https://k.autohome.com.cn/5769/#abc",
        original_review=original,
    )

    assert review.original_review == original
    assert review.content_hash == canonical_review_hash(original)
