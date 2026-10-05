from __future__ import annotations

from test_picker import FakePipeline

from chromatic_demo.npc_picker import GLiClassPicker, _request, _response


def test_request_accepts_public_schema() -> None:
    request = {
        "text": "Yes",
        "labels": {"accept": "Accept the quest."},
        "context": "An NPC offers a quest.",
    }

    assert _request(request) == (
        "Yes",
        {"accept": "Accept the quest."},
        "An NPC offers a quest.",
    )


def test_response_does_not_expose_invalid_request_details() -> None:
    picker = GLiClassPicker(FakePipeline([0.9, 0.1]))

    response = _response(picker, {"text": 4, "labels": {}})

    assert response == {"ok": False, "error": "invalid_request"}
