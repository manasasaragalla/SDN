"""Regression evaluation over the documented offline mock-parser corpus."""

import json
from pathlib import Path

import pytest

from backend.llm.mock import MockLLM
from backend.models.intent_normalization import normalize_intent


_CASES_PATH = Path(__file__).parent / "data" / "mock_intent_cases.json"
_CASES = json.loads(_CASES_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["name"])
def test_mock_parser_evaluation_case(case):
    normalized = normalize_intent(
        MockLLM().parse_intent(
            case["prompt"],
            source=case["source"],
            destination=case["destination"],
        )
    ).canonical

    assert normalized.scope.source == case["source"]
    assert normalized.scope.destination == case["destination"]
    assert [
        [item.metric, item.comparison.value, item.value]
        for item in normalized.constraints
    ] == case["constraints"]
    assert (
        [
            normalized.optimization.metric,
            normalized.optimization.direction.value,
        ]
        if normalized.optimization
        else None
    ) == case["optimization"]
