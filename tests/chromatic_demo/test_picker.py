from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from chromatic_demo.npc_picker import (
    ABSTAIN_LABEL,
    MODEL_ID,
    MODEL_REVISION,
    GLiClassPicker,
    KeywordRulePicker,
    _verify_pinned_snapshot,
    _verify_snapshot_files,
)


class FakePipeline:
    def __init__(self, scores: Sequence[float]) -> None:
        self._scores = scores
        self.calls: list[tuple[str, list[str], str | None]] = []

    def __call__(
        self,
        texts: str,
        labels: list[str],
        *,
        classification_type: str,
        prompt: str | None,
        return_hierarchical: bool,
    ) -> list[dict[str, float]]:
        assert classification_type == "multi-label"
        assert return_hierarchical is True
        self.calls.append((texts, labels, prompt))
        return [dict(zip(labels, self._scores, strict=True))]


LABELS = {
    "accept": "Agree to help the lighthouse keeper repair the beacon.",
    "decline": "Refuse the lighthouse keeper's request.",
    "ask": "Ask the lighthouse keeper for more information.",
}


def test_selects_clear_model_winner() -> None:
    pipeline = FakePipeline([0.82, 0.08, 0.10])
    picker = GLiClassPicker(pipeline)

    result = picker.classify(
        "Yes, I will repair it.",
        LABELS,
        "The keeper asks for help.",
    )

    assert result.label == "accept"
    assert result.model_label == "accept"
    assert result.reason == "selected"
    assert result.scores == {
        "accept": 0.82,
        "decline": 0.08,
        "ask": 0.10,
    }
    assert result.abstain_score is None
    assert result.model_id == "unverified/pipeline"
    assert pipeline.calls[0][0] == "Yes, I will repair it."
    assert pipeline.calls[0][2] is None


def test_returns_low_confidence_abstention_and_all_scores() -> None:
    picker = GLiClassPicker(FakePipeline([0.20, 0.15, 0.10]))

    result = picker.classify("Make me a sandwich.", LABELS)

    assert result.label is None
    assert result.model_label == "accept"
    assert result.reason == "low_confidence"
    assert result.abstained is True
    assert result.scores["accept"] == 0.20


def test_abstains_when_model_is_ambiguous() -> None:
    picker = GLiClassPicker(FakePipeline([0.88, 0.86, 0.04]))

    result = picker.classify("Maybe.", LABELS)

    assert result.label is None
    assert result.model_label == "accept"
    assert result.reason == "ambiguous"
    assert result.margin == pytest.approx(0.02)


def test_abstains_when_top_score_is_too_low() -> None:
    picker = GLiClassPicker(FakePipeline([0.40, 0.25, 0.20]))

    result = picker.classify("I suppose.", LABELS)

    assert result.label is None
    assert result.reason == "low_confidence"


def test_rejects_reserved_or_empty_inputs() -> None:
    picker = GLiClassPicker(FakePipeline([1.0]))

    with pytest.raises(ValueError, match="text must not be empty"):
        picker.classify(" ", {"accept": "Accept."})
    with pytest.raises(ValueError, match="reserved"):
        picker.classify("Okay", {ABSTAIN_LABEL: "Fake abstain."})


def test_rule_fallback_is_separate_and_deterministic() -> None:
    picker = KeywordRulePicker(min_score=0.25, min_margin=0.10)

    result = picker.classify("Please repair the beacon", LABELS)

    assert result.label == "accept"
    assert result.model_id == "authored-rules/token-overlap-v1"


def _synthetic_snapshot(path: Path) -> tuple[tuple[str, str], ...]:
    contents = {
        "config.json": json.dumps({"encoder_config": {}}).encode(),
        "model.safetensors": b"synthetic-test-weights",
        "special_tokens_map.json": b"{}",
        "tokenizer.json": b'{"fixture":true}',
        "tokenizer_config.json": b"{}",
    }
    expected = []
    for name, content in contents.items():
        (path / name).write_bytes(content)
        expected.append((name, hashlib.sha256(content).hexdigest()))
    return tuple(expected)


def test_rejects_tampered_tokenizer(tmp_path: Path) -> None:
    expected = _synthetic_snapshot(tmp_path)
    (tmp_path / "tokenizer.json").write_text("tampered", encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match="digest mismatch for tokenizer.json",
    ):
        _verify_snapshot_files(tmp_path, expected)


def test_rejects_tampered_config(tmp_path: Path) -> None:
    expected = _synthetic_snapshot(tmp_path)
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")

    with pytest.raises(RuntimeError, match="digest mismatch for config.json"):
        _verify_snapshot_files(tmp_path, expected)


def test_rejects_unsafe_weight_format(tmp_path: Path) -> None:
    expected = _synthetic_snapshot(tmp_path)
    (tmp_path / "weights.bin").write_bytes(b"unsafe fixture")

    with pytest.raises(RuntimeError, match="unsafe model files"):
        _verify_snapshot_files(tmp_path, expected)


def test_pinned_identity_requires_full_manifest() -> None:
    root = Path(__file__).resolve().parents[2]
    model_dir = root / "venv/chromatic-picker-model"

    if not model_dir.is_dir():
        pytest.skip("Optional pinned model snapshot is not installed")
    verified = _verify_pinned_snapshot(model_dir)

    assert verified.model_id == MODEL_ID
    assert verified.revision == MODEL_REVISION


def test_rejects_weight_digest_override(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must match the pinned model"):
        GLiClassPicker.from_local_model(
            tmp_path,
            expected_sha256="0" * 64,
        )
