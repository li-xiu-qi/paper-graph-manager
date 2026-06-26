"""Tests for annotate module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from paper_graph.annotate import annotate_all, annotate_paper, get_client, get_default_model
from paper_graph.database import get_connection, upsert_paper


class TestGetDefaultModel:
    def test_default_value(self, monkeypatch):
        monkeypatch.delenv("LLM_MODEL", raising=False)
        assert get_default_model() == "step-3.7-flash"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "custom-model")
        assert get_default_model() == "custom-model"


class TestGetClient:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        client = get_client()
        assert client.api_key == "dummy"
        assert str(client.base_url).rstrip("/") == "https://api.stepfun.com/step_plan/v1"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("LLM_BASE_URL", "http://localhost:9999/v1")
        client = get_client()
        assert client.api_key == "test-key"
        assert str(client.base_url).rstrip("/") == "http://localhost:9999/v1"

    def test_override_params(self):
        client = get_client(api_key="override-key", base_url="http://example.com/v1")
        assert client.api_key == "override-key"
        assert str(client.base_url).rstrip("/") == "http://example.com/v1"


def test_annotate_paper_core_logic(tmp_db, sample_paper, monkeypatch):
    """annotate_paper should call OpenAI, parse JSON, and update DB."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps({
        "core_contribution": "测试核心贡献",
        "teams": [
            {
                "name": "测试团队",
                "institution": "测试机构",
                "members": ["作者A", "作者B"],
            }
        ],
    })

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    # Patch get_client in the annotate module
    monkeypatch.setattr("paper_graph.annotate.get_client", lambda *args, **kwargs: mock_client)

    # Patch get_connection to always use tmp_db
    import paper_graph.annotate as annotate_mod
    import paper_graph.database as db_mod

    def _get_connection(db_path=None):
        return db_mod.get_connection(tmp_db)

    monkeypatch.setattr(annotate_mod, "get_connection", _get_connection)

    result = annotate_paper(sample_paper["id"], model="test-model")

    assert result["core_contribution"] == "测试核心贡献"
    assert len(result["teams"]) == 1
    assert result["teams"][0]["name"] == "测试团队"

    # Verify DB updated
    conn = db_mod.get_connection(tmp_db)
    paper = db_mod.get_paper(conn, sample_paper["id"])
    conn.close()
    assert paper["core_contribution"] == "测试核心贡献"


def test_annotate_all_skips_done(tmp_db, monkeypatch):
    """annotate_all should skip papers that already have core_contribution."""
    papers = [
        {
            "id": "done_paper",
            "title": "Already Done",
            "abstract": "Abstract",
            "published_date": "2024-01-01",
            "updated_date": "2024-01-02",
            "categories": "cs.AI",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "https://arxiv.org/abs/2401.00001",
            "core_contribution": "已有贡献",
        },
        {
            "id": "pending_paper",
            "title": "Pending Paper",
            "abstract": "Abstract",
            "published_date": "2024-01-03",
            "updated_date": "2024-01-04",
            "categories": "cs.AI",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "https://arxiv.org/abs/2401.00002",
            "core_contribution": "",
        },
    ]

    conn = get_connection(tmp_db)
    for p in papers:
        upsert_paper(conn, p)
    # upsert_paper does not update core_contribution, set it explicitly
    conn.execute("UPDATE papers SET core_contribution = ? WHERE id = ?", ("已有贡献", "done_paper"))
    conn.commit()
    conn.close()

    # Patch get_client and get_connection in annotate module
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps({
        "core_contribution": "新贡献",
        "teams": [],
    })
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    import paper_graph.annotate as annotate_mod
    import paper_graph.database as db_mod

    monkeypatch.setattr(annotate_mod, "get_client", lambda *args, **kwargs: mock_client)

    def _get_connection(db_path=None):
        return db_mod.get_connection(tmp_db)

    monkeypatch.setattr(annotate_mod, "get_connection", _get_connection)

    count = annotate_all(model="test-model", db_path=tmp_db)

    # Only the pending paper should be annotated
    assert count == 1

class TestAnnotateDegradation:
    """Test annotate_paper resilience against malformed LLM responses."""

    def test_non_json_response(self, tmp_db, sample_paper, monkeypatch):
        """LLM returns plain text instead of JSON; should raise JSONDecodeError."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "This is not JSON at all."

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        import paper_graph.annotate as annotate_mod
        import paper_graph.database as db_mod

        monkeypatch.setattr(annotate_mod, "get_client", lambda *a, **kw: mock_client)

        def _get_connection(db_path=None):
            return db_mod.get_connection(tmp_db)

        monkeypatch.setattr(annotate_mod, "get_connection", _get_connection)

        with pytest.raises(Exception):
            annotate_paper(sample_paper["id"], model="test-model")

    def test_empty_content(self, tmp_db, sample_paper, monkeypatch):
        """LLM returns empty string; should raise JSONDecodeError."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = ""

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        import paper_graph.annotate as annotate_mod
        import paper_graph.database as db_mod

        monkeypatch.setattr(annotate_mod, "get_client", lambda *a, **kw: mock_client)

        def _get_connection(db_path=None):
            return db_mod.get_connection(tmp_db)

        monkeypatch.setattr(annotate_mod, "get_connection", _get_connection)

        with pytest.raises(Exception):
            annotate_paper(sample_paper["id"], model="test-model")

    def test_missing_teams_field(self, tmp_db, sample_paper, monkeypatch):
        """LLM returns JSON without 'teams'; should not crash."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({
            "core_contribution": "Only contribution",
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        import paper_graph.annotate as annotate_mod
        import paper_graph.database as db_mod

        monkeypatch.setattr(annotate_mod, "get_client", lambda *a, **kw: mock_client)

        def _get_connection(db_path=None):
            return db_mod.get_connection(tmp_db)

        monkeypatch.setattr(annotate_mod, "get_connection", _get_connection)

        result = annotate_paper(sample_paper["id"], model="test-model")
        assert result["core_contribution"] == "Only contribution"
        assert result.get("teams", []) == []

    def test_missing_core_contribution_field(self, tmp_db, sample_paper, monkeypatch):
        """LLM returns JSON without 'core_contribution'; should not crash."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({
            "teams": [{"name": "Team", "members": []}],
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        import paper_graph.annotate as annotate_mod
        import paper_graph.database as db_mod

        monkeypatch.setattr(annotate_mod, "get_client", lambda *a, **kw: mock_client)

        def _get_connection(db_path=None):
            return db_mod.get_connection(tmp_db)

        monkeypatch.setattr(annotate_mod, "get_connection", _get_connection)

        result = annotate_paper(sample_paper["id"], model="test-model")
        assert result.get("core_contribution", "") == ""
        assert len(result.get("teams", [])) == 1

    def test_markdown_code_block_wrapped_json(self, tmp_db, sample_paper, monkeypatch):
        """LLM wraps JSON in ```json ... ```; should be parsed correctly."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = (
            "```json\n"
            + json.dumps({
                "core_contribution": "Wrapped contribution",
                "teams": [{"name": "Team", "members": ["A"]}],
            })
            + "\n```"
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        import paper_graph.annotate as annotate_mod
        import paper_graph.database as db_mod

        monkeypatch.setattr(annotate_mod, "get_client", lambda *a, **kw: mock_client)

        def _get_connection(db_path=None):
            return db_mod.get_connection(tmp_db)

        monkeypatch.setattr(annotate_mod, "get_connection", _get_connection)

        result = annotate_paper(sample_paper["id"], model="test-model")
        assert result["core_contribution"] == "Wrapped contribution"
