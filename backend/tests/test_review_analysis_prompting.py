from pathlib import Path

from backend.review_analysis.domain import CriterionSnapshot
from backend.review_analysis.prompting import PromptRenderer


def test_prompt_versions_and_hashes_are_manifested(tmp_path: Path):
    renderer = PromptRenderer()
    discovery = renderer.discovery_batch(["评论一"])
    merged = renderer.criteria_merge([{"name": "空间", "terms": ["宽敞"], "evidence": ["后排宽敞"]}])
    annotation = renderer.review_annotation(
        [CriterionSnapshot(name="空间", labels=["宽敞", "局促"])],
        "后排坐三个人也不挤",
    )

    assert discovery.manifest.version == "criteria-discovery-v1"
    assert merged.manifest.version == "criteria-merge-v1"
    assert annotation.manifest.version == "review-annotation-v1"
    assert all(len(item.manifest.sha256) == 64 for item in (discovery, merged, annotation))

    source = Path(renderer.template_dir) / "criteria_discovery_v1.txt"
    copied = tmp_path / source.name
    copied.write_text(source.read_text(encoding="utf-8") + "\n新增约束", encoding="utf-8")
    changed = PromptRenderer(tmp_path).discovery_batch(["评论一"])
    assert changed.manifest.sha256 != discovery.manifest.sha256


def test_annotation_prompt_contains_full_contract_without_chain_of_thought():
    prompt = PromptRenderer().review_annotation(
        [
            CriterionSnapshot(name="空间", labels=["宽敞", "一般", "局促"]),
            CriterionSnapshot(name="续航", labels=["充足", "不足"]),
        ],
        "满意：后排很宽敞\n不满意：冬季续航不足",
    )
    text = prompt.user_prompt

    assert "满意：后排很宽敞\n不满意：冬季续航不足" in text
    assert text.index("空间") < text.index("续航")
    assert '"annotations"' in text and '"unmatched_evidence"' in text
    assert "不允许创建新准则" in text
    assert "原文子串" in text
    assert "chain_of_thought" not in text
    assert "basis" in text
