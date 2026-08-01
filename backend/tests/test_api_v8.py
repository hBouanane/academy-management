"""Round 8: user-managed niveaux with teaching structure — TDD first."""

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        yield test_client


class TestCustomLevels:
    def test_seeded_levels_declare_their_teaching_structure(self, client):
        levels = {
            lv["name"]: lv["teaching_annees"] for lv in client.get("/api/levels").json()
        }
        assert levels == {"Primaire": 0, "Collège": 3, "Lycée": 3, "Formation": 0}

    def test_the_client_can_add_a_niveau(self, client):
        created = client.post(
            "/api/levels", json={"name": "Soutien", "teaching_annees": 0}
        )
        assert created.status_code == 201, created.text
        created = client.post(
            "/api/levels", json={"name": "Langues", "teaching_annees": 4}
        )
        assert created.status_code == 201, created.text
        levels = client.get("/api/levels").json()
        assert [lv["name"] for lv in levels][-2:] == ["Soutien", "Langues"]
        assert levels[-1]["teaching_annees"] == 4

    def test_duplicate_niveau_names_are_refused_in_french(self, client):
        response = client.post(
            "/api/levels", json={"name": "Primaire", "teaching_annees": 0}
        )
        assert response.status_code == 422
        assert "existe déjà" in response.json()["detail"]
