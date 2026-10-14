from backend.collection.asset_domain import (
    BatchMetadataPatchBody,
    MetadataPatchBody,
)
from backend.collection.asset_repository import ReviewAssetRepository
from backend.collection.domain import CollectedReview, CreateJobBody, VehicleSeries
from backend.collection.repository import CollectionRepository


def seed_asset_database(path):
    collection = CollectionRepository(path)
    series_rows = [
        VehicleSeries(
            series_id="5769",
            series_name="Model Y",
            series_url="https://www.autohome.com.cn/5769/",
            review_url="https://k.autohome.com.cn/5769/",
            discovery_rank=1,
        ),
        VehicleSeries(
            series_id="526",
            series_name="汉",
            series_url="https://www.autohome.com.cn/526/",
            review_url="https://k.autohome.com.cn/526/",
            discovery_rank=2,
        ),
    ]
    collection.create_job(
        "job-1",
        CreateJobBody(mode="verification", selected_series_ids=["5769"]).to_config(),
        "2026-10-08T08:00:00+00:00",
    )
    collection.save_discovery(
        "job-1", series_rows, "2026-10-08T08:01:00+00:00"
    )
    collection.save_review_page(
        "job-1",
        series_rows[0],
        [
            CollectedReview(
                review_id="review-1",
                series_id="5769",
                series_name="Model Y",
                source_url="https://k.autohome.com.cn/5769/#review-1",
                original_review={
                    "feeling_summary": "空间宽敞",
                    "contents": [{"structuredname": "满意", "content": "续航稳定"}],
                },
            )
        ],
        2,
        "2026-10-08T08:02:00+00:00",
    )
    collection.save_review_page(
        "job-1",
        series_rows[1],
        [
            CollectedReview(
                review_id="review-2",
                series_id="526",
                series_name="汉",
                source_url="https://k.autohome.com.cn/526/#review-2",
                original_review={
                    "feeling_summary": "动力充足",
                    "contents": [{"structuredname": "不满意", "content": "车机一般"}],
                },
            )
        ],
        3,
        "2026-10-08T08:03:00+00:00",
    )
    return ReviewAssetRepository(path)


def test_asset_filters_and_pagination_are_server_side(tmp_path):
    repository = seed_asset_database(tmp_path / "assets.sqlite3")
    repository.update_metadata(
        "autohome:review-1",
        MetadataPatchBody(
            revision=1,
            tags=["核心样本"],
            note="季度研究",
            analysis_enabled=True,
        ),
    )
    repository.update_metadata(
        "autohome:review-2",
        MetadataPatchBody(
            revision=1,
            tags=["待复核"],
            note="",
            analysis_enabled=False,
        ),
    )

    result = repository.list_assets(
        keyword="续航",
        series_id="5769",
        source_kind="autohome",
        tag="核心样本",
        analysis_enabled=True,
        page=1,
        page_size=1,
    )

    assert result["total"] == 1
    assert result["page"] == 1
    assert result["page_size"] == 1
    assert result["rows"][0]["asset_id"] == "autohome:review-1"
    assert result["rows"][0]["tags"] == ["核心样本"]
    assert "original_review" not in result["rows"][0]


def test_asset_detail_is_lossless_and_metadata_uses_revision(tmp_path):
    repository = seed_asset_database(tmp_path / "detail.sqlite3")

    detail = repository.get_asset("autohome:review-1")
    updated = repository.update_metadata(
        "autohome:review-1",
        MetadataPatchBody(
            revision=detail["revision"],
            tags=["重点", "空间"],
            note="保留原文",
            analysis_enabled=False,
        ),
    )

    assert detail["original_review"] == {
        "feeling_summary": "空间宽敞",
        "contents": [{"structuredname": "满意", "content": "续航稳定"}],
    }
    assert detail["reference_count"] == 0
    assert updated["revision"] == 2
    assert updated["analysis_enabled"] is False
    assert updated["tags"] == ["重点", "空间"]


def test_batch_metadata_updates_tags_without_raw_mutation(tmp_path):
    repository = seed_asset_database(tmp_path / "batch.sqlite3")
    before = repository.get_asset("autohome:review-1")

    result = repository.batch_update_metadata(
        BatchMetadataPatchBody(
            asset_ids=["autohome:review-1", "autohome:review-2"],
            analysis_enabled=False,
            add_tags=["本轮分析"],
            remove_tags=[],
        )
    )

    after = repository.get_asset("autohome:review-1")
    assert result == {"updated_count": 2}
    assert after["analysis_enabled"] is False
    assert after["tags"] == ["本轮分析"]
    assert after["original_review"] == before["original_review"]
    assert after["content_hash"] == before["content_hash"]


def test_summary_reports_management_and_source_counts(tmp_path):
    repository = seed_asset_database(tmp_path / "summary.sqlite3")
    repository.update_metadata(
        "autohome:review-2",
        MetadataPatchBody(
            revision=1, tags=[], note="", analysis_enabled=False
        ),
    )

    summary = repository.summary()

    assert summary["total"] == 2
    assert summary["analysis_enabled"] == 1
    assert summary["analysis_disabled"] == 1
    assert summary["by_source"] == [{"source_kind": "autohome", "count": 2}]
    assert {row["series_id"]: row["count"] for row in summary["by_series"]} == {
        "526": 1,
        "5769": 1,
    }
