import csv
import importlib.util
from pathlib import Path

from emporio.data import ROOT


def test_publication_contacts_are_synthetic_and_ids_are_preserved(tmp_path):
    spec = importlib.util.spec_from_file_location("prepare_public", ROOT / "scripts" / "prepare_public.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = next((ROOT / "data").glob("* - customers.csv"))
    original = source.read_bytes()
    path = tmp_path / "customers.csv"
    path.write_bytes(original)
    module.anonymize(path)
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 50
    assert {r["customer_id"] for r in rows} == {str(i) for i in range(1, 51)}
    assert all(r["email"].endswith("@example.invalid") and r["phone"].startswith("(00)") for r in rows)
    assert all(r["name"].startswith("Cliente de demonstração") for r in rows)
    assert source.read_bytes() == original
