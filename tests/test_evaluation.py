import json
from types import SimpleNamespace

import pytest

from emporio.data import DataError
from emporio.evaluation import run


def test_evaluation_records_runs_and_requires_semantic_review(tmp_path, monkeypatch):
    cases = [{"id": "test", "customer_id": None, "messages": ["Oi"],
              "required_tools": ["get_product_details"], "expectation": "Correto"}]
    root = tmp_path / "project"
    (root / "evaluation").mkdir(parents=True)
    (root / "evaluation" / "cases.json").write_text(json.dumps(cases))
    monkeypatch.setattr("emporio.evaluation.ROOT", root)

    class Fake:
        model = "test-model"
        last_status = "completed"
        last_trace = [{"name": "get_product_details", "result": {"ok": True}}]
        last_usage = []

        def reply(self, message):
            return "Resposta simulada exclusiva do teste unitário."

    output = tmp_path / "results"
    assert run(lambda customer: Fake(), output) == 0
    result = json.loads((output / "results.json").read_text())[0]
    assert result["automatic_pass"] and result["semantic_review"] == "pending"
    assert "PENDENTE" in (output / "review.md").read_text()
    assert not (root / "examples").exists()
    with pytest.raises(DataError, match="já contém"):
        run(lambda customer: Fake(), output)
    with pytest.raises(DataError, match="desconhecido"):
        run(lambda customer: Fake(), output, ["absent"])


def test_cases_cover_five_examples_and_at_least_twelve_scenarios():
    from emporio.data import ROOT
    cases = json.loads((ROOT / "evaluation" / "cases.json").read_text())
    assert len(cases) >= 12
    assert len({case["id"] for case in cases}) == len(cases)
    assert sum(case.get("example", False) for case in cases) == 5
