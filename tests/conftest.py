import pytest
from fastapi.testclient import TestClient

from fleetline.generate import generate_dataset
from fleetline.service import reset_state


@pytest.fixture(scope="session")
def portfolio(tmp_path_factory):
    path = tmp_path_factory.mktemp("portfolio")
    generate_dataset(path, seed=42)
    return path


@pytest.fixture(autouse=True)
def isolated(portfolio, monkeypatch):
    monkeypatch.setenv("FLEETLINE_DATA_DIR", str(portfolio))
    reset_state()
    return portfolio


@pytest.fixture
def client():
    from fleetline.api import app

    return TestClient(app)
