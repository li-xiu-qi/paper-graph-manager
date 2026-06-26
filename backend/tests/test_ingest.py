"""Tests for ingest module."""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from paper_graph.ingest import (
    _parse_arxiv_id,
    _download_arxiv_pdf,
    _extract_authors_from_text,
    extract_pdf_metadata,
    ingest_arxiv_id,
    ingest_local_pdf,
    search_arxiv,
    search_arxiv_only,
)


class TestParseArxivId:
    def test_with_full_url(self):
        assert _parse_arxiv_id("https://arxiv.org/abs/2401.00001") == "2401.00001"

    def test_with_prefix(self):
        assert _parse_arxiv_id("arxiv_2401.00001") == "2401.00001"

    def test_plain_id(self):
        assert _parse_arxiv_id("2401.00001") == "2401.00001"

    def test_id_with_version(self):
        assert _parse_arxiv_id("2401.00001v2") == "2401.00001"


class TestSearchArxivOnly:
    def test_returns_correct_format(self):
        mock_result = MagicMock()
        mock_result.entry_id = "http://arxiv.org/abs/2401.00001"
        mock_result.title = "Mock Paper Title"
        mock_result.summary = "Mock abstract text here."
        mock_result.published = datetime.datetime(2024, 1, 1)
        mock_result.updated = datetime.datetime(2024, 1, 2)
        mock_result.categories = ["cs.AI", "cs.CL"]
        mock_result.authors = ["Author One", "Author Two"]

        with patch("paper_graph.ingest.arxiv.Client") as MockClient, \
             patch("paper_graph.ingest.arxiv.Search") as MockSearch, \
             patch("paper_graph.ingest.arxiv.SortCriterion") as MockSort:
            MockSort.Relevance = "relevance"
            mock_client_instance = MockClient.return_value
            mock_client_instance.results.return_value = [mock_result]

            results = search_arxiv_only("test query", max_results=5)

        assert len(results) == 1
        r = results[0]
        assert r["id"] == "arxiv_2401.00001"
        assert r["title"] == "Mock Paper Title"
        assert r["abstract"] == "Mock abstract text here."
        assert r["published_date"] == "2024-01-01"
        assert r["categories"] == "cs.AI, cs.CL"
        assert r["arxiv_url"] == "http://arxiv.org/abs/2401.00001"
        assert r["authors"] == ["Author One", "Author Two"]


class TestIngestArxivId:
    def test_writes_to_db(self, tmp_db):
        mock_result = MagicMock()
        mock_result.entry_id = "http://arxiv.org/abs/2401.00001"
        mock_result.title = "Mock Paper Title"
        mock_result.summary = "Mock abstract text here."
        mock_result.published = datetime.datetime(2024, 1, 1)
        mock_result.updated = datetime.datetime(2024, 1, 2)
        mock_result.categories = ["cs.AI"]
        mock_result.authors = ["Author One"]
        mock_result.affiliation = ["Inst A"]

        with patch("paper_graph.ingest.arxiv.Client") as MockClient, \
             patch("paper_graph.ingest.arxiv.Search") as MockSearch:
            MockClient.return_value.results.return_value = [mock_result]
            MockSearch.return_value

            paper_id = ingest_arxiv_id("2401.00001", db_path=tmp_db)

        assert paper_id == "arxiv_2401.00001"

        import paper_graph.database as db_mod
        conn = db_mod.get_connection(tmp_db)
        paper = db_mod.get_paper(conn, paper_id)
        conn.close()

        assert paper is not None
        assert paper["title"] == "Mock Paper Title"
        assert paper["source"] == "arxiv"
        assert paper["arxiv_url"] == "http://arxiv.org/abs/2401.00001"


class TestExtractPdfMetadata:
    def test_extracts_title_and_date(self, tmp_path):
        pdf_file = tmp_path / "dummy.pdf"
        pdf_file.write_text("not a real pdf")

        mock_doc = MagicMock()
        mock_doc.metadata = {"title": "", "creationDate": "D:20230101000000"}
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value.get_text.return_value = (
            "PDF Real Title\nAlice Smith\nBob Jones\nAbstract\nSome abstract text."
        )
        mock_doc.close.return_value = None

        with patch("paper_graph.ingest.fitz.open", return_value=mock_doc):
            meta = extract_pdf_metadata(pdf_file)

        assert meta["title"] == "PDF Real Title"
        assert meta["published_date"] == "2023-01-01"
        assert meta["source"] == "local"
        assert meta["pdf_path"] == str(pdf_file.resolve())
        assert "Alice Smith" in meta["abstract"]
        mock_doc.close.assert_called()


class TestExtractAuthorsFromText:
    def test_newline_separated_english_names(self):
        text = "PDF Title\nAlice Smith\nBob Jones\nAbstract\nText"
        assert _extract_authors_from_text(text) == ["Alice Smith", "Bob Jones"]

    def test_newline_separated_chinese_names(self):
        text = "Title\n张三\n李四\nAbstract\n正文"
        assert _extract_authors_from_text(text) == ["张三", "李四"]

    def test_names_with_initials(self):
        text = "Title\nAlice B. Chan\nDavid E. Lee\nIntroduction"
        assert _extract_authors_from_text(text) == ["Alice B. Chan", "David E. Lee"]

    def test_stops_at_abstract_keyword(self):
        text = "Title\nAlice Smith\nAbstract\nBob Jones"
        assert _extract_authors_from_text(text) == ["Alice Smith"]

    def test_no_authors_found(self):
        assert _extract_authors_from_text("Abstract\nJust text") == []


class TestSearchArxiv:
    def test_upserts_papers_into_db(self, tmp_db):
        mock_result = MagicMock()
        mock_result.entry_id = "http://arxiv.org/abs/2401.00002"
        mock_result.title = "Search Result Title"
        mock_result.summary = "Search abstract."
        mock_result.published = datetime.datetime(2024, 1, 15)
        mock_result.updated = datetime.datetime(2024, 1, 16)
        mock_result.categories = ["cs.LG"]
        mock_result.authors = ["Searcher One"]
        mock_result.affiliation = None

        with patch("paper_graph.ingest.arxiv.Client") as MockClient, \
             patch("paper_graph.ingest.arxiv.Search") as MockSearch, \
             patch("paper_graph.ingest.arxiv.SortCriterion") as MockSort:
            MockSort.Relevance = "relevance"
            MockClient.return_value.results.return_value = [mock_result]
            MockSearch.return_value

            paper_ids = search_arxiv("transformers", max_results=1, db_path=tmp_db)

        assert paper_ids == ["arxiv_2401.00002"]

        import paper_graph.database as db_mod
        conn = db_mod.get_connection(tmp_db)
        paper = db_mod.get_paper(conn, "arxiv_2401.00002")
        conn.close()
        assert paper is not None
        assert paper["title"] == "Search Result Title"
        assert paper["source"] == "arxiv"


class TestDownloadArxivPdf:
    def test_writes_pdf_file(self, tmp_path):
        result = MagicMock()
        result.pdf_url = "http://arxiv.org/pdf/2401.00003.pdf"

        mock_response = MagicMock()
        mock_response.content = b"PDF binary data"
        mock_response.raise_for_status.return_value = None

        pdf_path = tmp_path / "paper.pdf"

        with patch("paper_graph.ingest.requests.get", return_value=mock_response):
            _download_arxiv_pdf(result, pdf_path)

        assert pdf_path.exists()
        assert pdf_path.read_bytes() == b"PDF binary data"
        mock_response.raise_for_status.assert_called_once()


class TestIngestLocalPdf:
    def test_ingests_local_pdf(self, tmp_path, monkeypatch):
        pdf_file = tmp_path / "local.pdf"
        pdf_file.write_text("not real pdf")

        mock_doc = MagicMock()
        mock_doc.metadata = {"title": ""}
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value.get_text.return_value = (
            "Local PDF Title\nAlice Smith\nBob Jones\nAbstract\nAbstract text here."
        )
        mock_doc.close.return_value = None

        with patch("paper_graph.ingest.fitz.open", return_value=mock_doc):
            paper_id = ingest_local_pdf(pdf_file, db_path=tmp_path / "papers.db")

        assert paper_id.startswith("local_")

        import paper_graph.database as db_mod
        conn = db_mod.get_connection(tmp_path / "papers.db")
        paper = db_mod.get_paper(conn, paper_id)
        conn.close()
        assert paper is not None
        assert paper["title"] == "Local PDF Title"
        assert paper["source"] == "local"

    def test_ingest_local_pdf_handles_empty_metadata(self, tmp_path, monkeypatch):
        pdf_file = tmp_path / "empty.pdf"
        pdf_file.write_text("not real pdf")

        mock_doc = MagicMock()
        mock_doc.metadata = {}
        mock_doc.__len__.return_value = 0
        mock_doc.close.return_value = None

        with patch("paper_graph.ingest.fitz.open", return_value=mock_doc):
            paper_id = ingest_local_pdf(pdf_file, db_path=tmp_path / "papers.db")

        assert paper_id.startswith("local_")

        import paper_graph.database as db_mod
        conn = db_mod.get_connection(tmp_path / "papers.db")
        paper = db_mod.get_paper(conn, paper_id)
        conn.close()
        assert paper["title"] == ""
