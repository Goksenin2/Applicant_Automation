import io
import json

import anthropic
import httpx2 as httpx
import pytest
from docx import Document

from run import build_updates
from screener import cv
from screener.monday import file_asset_ids
from screener.scorer import CRITERIA, Assessment, Scorer, ScoringError, notes, total

CFG = {
    "score_columns": {k: f"num_{i}" for i, k in enumerate(CRITERIA)},
    "total_column": "num_total",
    "notes_column": "notes",
    "status_column": "status",
    "status_done_label": "AI scored",
    "status_review_label": "Needs human review",
}


def make_assessment(scores=(5, 4, 3, 2, 1), review=False) -> dict:
    data = {k: {"score": s, "reason": f"reason {k}"} for k, s in zip(CRITERIA, scores)}
    return data | {"needs_human_review": review, "review_reason": "odd" if review else ""}


def test_file_asset_ids():
    value = {"value": json.dumps({"files": [{"assetId": 42, "name": "cv.pdf"}, {"linkToFile": "https://drive"}]})}
    assert file_asset_ids(value) == [42]
    assert file_asset_ids({"value": None}) == []
    assert file_asset_ids(None) == []


def test_total_and_updates():
    a = Assessment.model_validate(make_assessment())
    assert total(a) == 3.0
    updates = build_updates(CFG, a)
    assert updates["num_0"] == "5" and updates["num_total"] == "3.0"
    assert updates["status"] == {"label": "AI scored"}
    assert "Social impact: 1" in updates["notes"]["text"]


def test_formula_total_not_written_and_review_label():
    a = Assessment.model_validate(make_assessment(review=True))
    updates = build_updates(CFG | {"total_column": None}, a)
    assert "num_total" not in updates and None not in updates
    assert updates["status"] == {"label": "Needs human review"}
    assert "REVIEW: odd" in notes(a)


def test_docx_cv(tmp_path):
    doc = Document()
    doc.add_paragraph("Jane Doe - BSc Economics")
    buf = io.BytesIO()
    doc.save(buf)
    path = tmp_path / "cv.docx"
    path.write_bytes(buf.getvalue())
    block = cv.to_content_block(path)
    assert block["type"] == "text" and "BSc Economics" in block["text"]


def test_pdf_cv_and_unsupported(tmp_path):
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    assert cv.to_content_block(pdf)["source"]["media_type"] == "application/pdf"
    with pytest.raises(cv.UnreadableCV):
        (tmp_path / "cv.pages").write_bytes(b"x")
        cv.to_content_block(tmp_path / "cv.pages")


def _scorer_with_response(result: dict, captured: list, stop_reason="end_turn") -> Scorer:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": json.dumps(result)}],
            "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10},
        })

    scorer = Scorer("RUBRIC TEXT", 1, 5, "claude-opus-5-5")
    scorer.client = anthropic.Anthropic(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    return scorer


def test_scorer_request_and_parse():
    captured = []
    scorer = _scorer_with_response(make_assessment(), captured)
    a = scorer.score("Jane", {"Why 180DC?": "Impact."}, None)
    assert a.skills_experience.score == 5
    body = captured[0]
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default"
    assert body["output_config"]["effort"] == "medium"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert "RUBRIC TEXT" in body["system"]
    assert "no readable CV" in body["messages"][0]["content"][0]["text"]


def test_scorer_rejects_out_of_range():
    scorer = _scorer_with_response(make_assessment(scores=(9, 4, 3, 2, 1)), [])
    with pytest.raises(ScoringError):
        scorer.score("Jane", {}, None)
