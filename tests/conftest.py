import pytest

from emporio.data import ROOT, build
from emporio.tools import StoreTools


@pytest.fixture(scope="session")
def prepared(tmp_path_factory):
    output = tmp_path_factory.mktemp("snapshot")
    build(ROOT / "data", output)
    return output


@pytest.fixture
def store(prepared):
    return StoreTools(prepared / "store.sqlite3", customer_id=3)
