"""Choose an allowed NPC action label without changing game state."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, TextIO, cast

MODEL_ID = "knowledgator/gliclass-edge-v3.0"
MODEL_REVISION = "df03993a2ed98e5e4a0d2dd7efbbd105abe874cf"
MODEL_SHA256 = (
    "ed2600439be991eaab06d831b259e99057a69242acf3a26a61b053695b1b979c"
)
MODEL_FILE_SHA256 = (
    (
        "config.json",
        "82c73012fe4ce7f286e5615e17e53360f6f18129bc6d912719e0656e040d9deb",
    ),
    ("model.safetensors", MODEL_SHA256),
    (
        "special_tokens_map.json",
        "ea97ecdbcc73713039d8d64dbb05e3689495c96657fbd9a18f5bed381be81049",
    ),
    (
        "tokenizer.json",
        "7c1979be5ac04a6681dbfbb98a2b01b176883a298f2a7240c93048b244118a01",
    ),
    (
        "tokenizer_config.json",
        "998e030cf9cefbf6e58cbc5b9b2218e8052eb31449c2d08a2f21f60addb79787",
    ),
)
ABSTAIN_LABEL = "__abstain__"
MAX_ACTION_LABELS = 24

PickerReason = Literal[
    "selected",
    "low_confidence",
    "ambiguous",
]


class ClassificationPipeline(Protocol):
    """Narrow callable surface used from the GLiClass pipeline."""

    def __call__(
        self,
        texts: str,
        labels: list[str],
        *,
        classification_type: str,
        prompt: str | None,
        return_hierarchical: bool,
    ) -> list[dict[str, float]]: ...


@dataclass(frozen=True, slots=True)
class PickerResult:
    """Observed classifier scores plus the policy-gated action label."""

    label: str | None
    model_label: str
    scores: dict[str, float]
    abstain_score: float | None
    confidence: float
    margin: float
    abstained: bool
    reason: PickerReason
    model_id: str
    model_revision: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable receipt."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class _VerifiedModel:
    model_id: str
    revision: str


class GLiClassPicker:
    """CPU-only GLiClass picker with explicit abstention gates.

    The class returns a label from the caller-provided mapping, or ``None``.
    It has no reference to quest state and cannot apply the chosen action.
    """

    def __init__(
        self,
        pipeline: ClassificationPipeline,
        *,
        model_id: str = "unverified/pipeline",
        model_revision: str = "unverified",
        min_confidence: float = 0.80,
        min_margin: float = 0.03,
    ) -> None:
        _validate_probability("min_confidence", min_confidence)
        _validate_probability("min_margin", min_margin)
        self._pipeline = pipeline
        self._model_id = model_id
        self._model_revision = model_revision
        self._min_confidence = min_confidence
        self._min_margin = min_margin

    @classmethod
    def from_local_model(
        cls,
        model_dir: str | Path,
        *,
        min_confidence: float = 0.80,
        min_margin: float = 0.03,
        cpu_threads: int = 2,
        expected_sha256: str = MODEL_SHA256,
    ) -> GLiClassPicker:
        """Load the pinned model once from a verified local snapshot.

        The loader is offline, rejects unsafe weight formats and remote-code
        mappings, and requires exact hashes for all runtime model files.
        """

        path = Path(model_dir).resolve()
        if expected_sha256 != MODEL_SHA256:
            raise ValueError("expected_sha256 must match the pinned model")
        verified = _verify_pinned_snapshot(path)

        if not 1 <= cpu_threads <= 8:
            raise ValueError("cpu_threads must be between 1 and 8")

        import torch
        from gliclass import GLiClassModel, ZeroShotClassificationPipeline
        from transformers import AutoTokenizer

        torch.set_num_threads(cpu_threads)
        model = GLiClassModel.from_pretrained(
            path,
            local_files_only=True,
            trust_remote_code=False,
            use_safetensors=True,
        )
        tokenizer = AutoTokenizer.from_pretrained(
            path,
            local_files_only=True,
            trust_remote_code=False,
        )
        pipeline = ZeroShotClassificationPipeline(
            model,
            tokenizer,
            max_classes=MAX_ACTION_LABELS,
            max_length=256,
            classification_type="multi-label",
            device="cpu",
            progress_bar=False,
        )
        return cls(
            cast(ClassificationPipeline, pipeline),
            model_id=verified.model_id,
            model_revision=verified.revision,
            min_confidence=min_confidence,
            min_margin=min_margin,
        )

    def classify(
        self,
        text: str,
        labels: Mapping[str, str],
        context: str = "",
    ) -> PickerResult:
        """Score allowed labels and return one label or explicit abstention."""

        del context
        action_labels = _validate_inputs(text, labels)
        rendered = [description for _, description in action_labels]
        raw = self._pipeline(
            text.strip(),
            rendered,
            classification_type="multi-label",
            prompt=None,
            return_hierarchical=True,
        )
        score_map = _extract_score_map(raw, rendered)
        return self._build_result(action_labels, rendered, score_map)

    def _build_result(
        self,
        action_labels: Sequence[tuple[str, str]],
        rendered: Sequence[str],
        score_map: Mapping[str, float],
    ) -> PickerResult:
        keyed_scores = {
            label: score_map[rendered[index]]
            for index, (label, _) in enumerate(action_labels)
        }
        ranked = sorted(
            keyed_scores.items(),
            key=lambda item: (-item[1], item[0]),
        )
        model_label, confidence = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = confidence - runner_up

        label: str | None = model_label
        reason: PickerReason = "selected"
        if confidence < self._min_confidence:
            label = None
            reason = "low_confidence"
        elif margin < self._min_margin:
            label = None
            reason = "ambiguous"

        return PickerResult(
            label=label,
            model_label=model_label,
            scores=keyed_scores,
            abstain_score=None,
            confidence=confidence,
            margin=margin,
            abstained=label is None,
            reason=reason,
            model_id=self._model_id,
            model_revision=self._model_revision,
        )


class KeywordRulePicker:
    """Small offline fallback based only on authored token-overlap rules.

    Scores are deterministic overlap ratios. They are not model
    probabilities and this class is never selected automatically.
    """

    def __init__(
        self,
        *,
        min_score: float = 0.35,
        min_margin: float = 0.10,
    ) -> None:
        _validate_probability("min_score", min_score)
        _validate_probability("min_margin", min_margin)
        self._min_score = min_score
        self._min_margin = min_margin

    def classify(
        self,
        text: str,
        labels: Mapping[str, str],
        context: str = "",
    ) -> PickerResult:
        """Return the unique rule match or abstain."""

        del context
        action_labels = _validate_inputs(text, labels)
        text_tokens = _tokens(text)
        scores: dict[str, float] = {}
        for label, description in action_labels:
            label_tokens = _tokens(f"{label} {description}")
            overlap = len(text_tokens & label_tokens)
            scores[label] = overlap / max(1, len(label_tokens))

        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        model_label, confidence = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = confidence - runner_up
        label: str | None = model_label
        reason: PickerReason = "selected"
        if confidence < self._min_score:
            label = None
            reason = "low_confidence"
        elif margin < self._min_margin:
            label = None
            reason = "ambiguous"

        return PickerResult(
            label=label,
            model_label=model_label,
            scores=scores,
            abstain_score=None,
            confidence=confidence,
            margin=margin,
            abstained=label is None,
            reason=reason,
            model_id="authored-rules/token-overlap-v1",
            model_revision="1",
        )


def _validate_inputs(
    text: str,
    labels: Mapping[str, str],
) -> list[tuple[str, str]]:
    if not text.strip():
        raise ValueError("text must not be empty")
    if not labels:
        raise ValueError("labels must not be empty")
    if len(labels) > MAX_ACTION_LABELS:
        message = f"labels must contain at most {MAX_ACTION_LABELS} actions"
        raise ValueError(message)

    validated: list[tuple[str, str]] = []
    descriptions: set[str] = set()
    for label, description in labels.items():
        clean_label = label.strip()
        clean_description = description.strip()
        if not clean_label or not clean_description:
            raise ValueError("label names and descriptions must not be empty")
        if clean_label == ABSTAIN_LABEL:
            raise ValueError(f"{ABSTAIN_LABEL} is reserved")
        if clean_description in descriptions:
            raise ValueError("label descriptions must be unique")
        descriptions.add(clean_description)
        validated.append((clean_label, clean_description))
    return validated


def _extract_score_map(
    raw: object,
    rendered_labels: Sequence[str],
) -> dict[str, float]:
    if not isinstance(raw, list) or len(raw) != 1:
        raise RuntimeError("GLiClass returned an unexpected result envelope")
    first = raw[0]
    if not isinstance(first, dict):
        raise RuntimeError("GLiClass returned an unexpected score map")

    scores: dict[str, float] = {}
    for rendered in rendered_labels:
        value = first.get(rendered)
        if not isinstance(value, int | float):
            raise RuntimeError(f"GLiClass omitted score for {rendered!r}")
        score = float(value)
        _validate_probability("model score", score)
        scores[rendered] = score
    return scores


def _validate_probability(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")


def _verify_pinned_snapshot(path: Path) -> _VerifiedModel:
    _verify_snapshot_files(path, MODEL_FILE_SHA256)
    return _VerifiedModel(MODEL_ID, MODEL_REVISION)


def _verify_snapshot_files(
    path: Path,
    expected_files: Sequence[tuple[str, str]],
) -> None:
    if not path.is_dir():
        raise FileNotFoundError(f"model directory does not exist: {path}")

    unsafe_suffixes = {".bin", ".ckpt", ".pkl", ".pickle", ".pt", ".pth"}
    unsafe = [
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file() and candidate.suffix.lower() in unsafe_suffixes
    ]
    if unsafe:
        names = ", ".join(
            str(candidate.relative_to(path)) for candidate in unsafe
        )
        raise RuntimeError(f"unsafe model files are not allowed: {names}")

    for name, expected_digest in expected_files:
        candidate = path / name
        if not candidate.is_file():
            raise FileNotFoundError(f"missing pinned model file: {candidate}")
        digest = _sha256(candidate)
        if digest != expected_digest:
            raise RuntimeError(
                f"digest mismatch for {name}: "
                f"expected {expected_digest}, observed {digest}"
            )

    for config_name in ("config.json", "tokenizer_config.json"):
        config_path = path / config_name
        with config_path.open(encoding="utf-8") as handle:
            config = json.load(handle)
        if _contains_auto_map(config):
            raise RuntimeError(f"remote-code mapping found in {config_name}")

    with (path / "config.json").open(encoding="utf-8") as handle:
        model_config = json.load(handle)
    if not isinstance(model_config.get("encoder_config"), dict):
        message = "model config must embed encoder_config for offline load"
        raise RuntimeError(message)


def _contains_auto_map(value: Any) -> bool:
    if isinstance(value, dict):
        return "auto_map" in value or any(
            _contains_auto_map(child) for child in value.values()
        )
    if isinstance(value, list):
        return any(_contains_auto_map(child) for child in value)
    return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "for",
    "in",
    "is",
    "of",
    "or",
    "the",
    "to",
}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in _TOKEN_PATTERN.findall(value.lower())
        if token not in _STOP_WORDS
    }


def _request(payload: object) -> tuple[str, dict[str, str], str]:
    if not isinstance(payload, dict):
        raise ValueError("request must be a JSON object")

    text = payload.get("text")
    labels = payload.get("labels")
    context = payload.get("context", "")
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    if not isinstance(labels, Mapping):
        raise ValueError("labels must be an object")
    if not isinstance(context, str):
        raise ValueError("context must be a string")

    typed_labels: dict[str, str] = {}
    for key, value in labels.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("labels must map strings to strings")
        typed_labels[key] = value
    return text, typed_labels, context


def _response(picker: GLiClassPicker, payload: object) -> dict[str, object]:
    try:
        text, labels, context = _request(payload)
        result = picker.classify(text, labels, context)
    except ValueError:
        return {"ok": False, "error": "invalid_request"}
    except RuntimeError:
        return {"ok": False, "error": "classification_failed"}
    return {"ok": True, "result": result.to_dict()}


def _emit(handle: TextIO, response: dict[str, object]) -> None:
    handle.write(json.dumps(response, separators=(",", ":")))
    handle.write("\n")
    handle.flush()


def _run_jsonl(picker: GLiClassPicker) -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            _emit(sys.stdout, {"ok": False, "error": "invalid_json"})
            continue
        _emit(sys.stdout, _response(picker, payload))


def _run_once(picker: GLiClassPicker) -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        _emit(sys.stdout, {"ok": False, "error": "invalid_json"})
        return
    _emit(sys.stdout, _response(picker, payload))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--jsonl", action="store_true")
    parser.add_argument("--cpu-threads", type=int, default=2)
    args = parser.parse_args()

    picker = GLiClassPicker.from_local_model(
        args.model_dir,
        cpu_threads=args.cpu_threads,
    )
    if args.jsonl:
        _run_jsonl(picker)
    else:
        _run_once(picker)


if __name__ == "__main__":
    main()
