"""论文图谱管理工具 - PDF 和 arXiv 入库模块。"""

import re
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional

import fitz  # PyMuPDF
import arxiv
import requests

from .database import init_db, get_connection, upsert_paper


def _download_arxiv_pdf(result: arxiv.Result, pdf_path: Path, timeout: int = 60) -> None:
    """兼容 arxiv 4.x：使用 pdf_url 手动下载 PDF。"""
    pdf_url = getattr(result, "pdf_url", None)
    if not pdf_url:
        # 4.0 中 pdf_url 可能是 links 中的第一个 link
        for link in getattr(result, "links", []):
            href = getattr(link, "href", "")
            if href.endswith(".pdf"):
                pdf_url = href
                break
    if not pdf_url:
        raise RuntimeError(f"无法获取 PDF URL: {result.entry_id}")

    response = requests.get(pdf_url, timeout=timeout)
    response.raise_for_status()
    pdf_path.write_bytes(response.content)


# ──────────────────────────────
# 本地 PDF 入库
# ──────────────────────────────

def extract_pdf_metadata(pdf_path: Path) -> dict:
    """用 Fitz 提取 PDF 元数据。"""
    doc = fitz.open(pdf_path)
    metadata = doc.metadata or {}

    first_page_text = ""
    if len(doc) > 0:
        first_page_text = doc[0].get_text()[:2000]

    title = metadata.get("title", "").strip()
    if not title or len(title) < 5:
        lines = [l.strip() for l in first_page_text.splitlines() if l.strip()]
        if lines:
            title = lines[0]

    # 解析 PDF 创建日期（格式可能是 D:20240101000000 或 2024-01-01）
    raw_date = metadata.get("creationDate", datetime.now().isoformat())
    created_date = _parse_pdf_date(raw_date)

    doc.close()

    file_hash = hashlib.md5(str(pdf_path.resolve()).encode()).hexdigest()[:12]

    return {
        "id": f"local_{file_hash}",
        "title": title,
        "abstract": first_page_text.replace("\n", " ").strip()[:1500],
        "published_date": created_date,
        "updated_date": datetime.now().isoformat(),
        "categories": "",
        "pdf_path": str(pdf_path.resolve()),
        "source": "local",
        "arxiv_url": None,
    }


def _parse_pdf_date(raw: str) -> str:
    """解析 PDF 元数据日期格式。"""
    # 匹配 D:20240101000000 格式
    m = re.search(r"D:(\d{4})(\d{2})(\d{2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # 已经是 YYYY-MM-DD 格式
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]
    return datetime.now().isoformat()[:10]


def ingest_local_pdf(pdf_path: str | Path, db_path: Optional[Path] = None) -> str:
    """入库单个本地 PDF，返回 paper_id。"""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 不存在: {pdf_path}")

    init_db(db_path)
    conn = get_connection(db_path)
    paper = extract_pdf_metadata(pdf_path)

    doc = fitz.open(pdf_path)
    first_page = doc[0].get_text() if len(doc) > 0 else ""
    doc.close()

    authors_raw = _extract_authors_from_text(first_page)
    _save_authors(conn, paper["id"], authors_raw)

    paper_data = {
        "id": paper["id"],
        "title": paper["title"],
        "abstract": first_page.replace("\n", " ").strip()[:1500],
        "published_date": paper["published_date"],
        "updated_date": datetime.now().isoformat(),
        "categories": "",
        "pdf_path": str(pdf_path.resolve()),
        "source": "local",
        "arxiv_url": None,
    }

    upsert_paper(conn, paper_data)
    conn.commit()
    conn.close()
    return paper["id"]


def _extract_authors_from_text(text: str) -> list[str]:
    authors = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines[:15]:
        if any(kw in line.lower() for kw in ["abstract", "introduction", "keywords", "received", "accepted"]):
            break
        if re.match(r"^[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+){1,3}$", line):
            authors.append(line)
        elif re.match(r"^[\u4e00-\u9fa5]{2,4}(?:\s+[\u4e00-\u9fa5]{2,4}){0,3}$", line):
            authors.append(line)
    return authors


def _save_authors(conn, paper_id: str, authors: list[str]) -> None:
    cur = conn.cursor()
    for order, name in enumerate(authors):
        cur.execute("INSERT OR IGNORE INTO authors (name) VALUES (?)", (name,))
        cur.execute("SELECT id FROM authors WHERE name = ?", (name,))
        author_id = cur.fetchone()[0]
        cur.execute(
            "INSERT OR IGNORE INTO paper_authors (paper_id, author_id, author_order) VALUES (?, ?, ?)",
            (paper_id, author_id, order),
        )


# ──────────────────────────────
# arXiv 入库
# ──────────────────────────────

def _parse_arxiv_id(identifier: str) -> str:
    m = re.search(r"(\d{4}\.\d{4,5})", identifier)
    if m:
        return m.group(1)
    return identifier.strip()


def ingest_arxiv_id(arxiv_id: str, db_path: Optional[Path] = None, download_pdf: bool = False,
                    pdf_dir: Optional[Path] = None) -> str:
    """通过 arXiv ID 入库论文。"""
    init_db(db_path)
    conn = get_connection(db_path)

    client = arxiv.Client(page_size=1, delay_seconds=1)
    search = arxiv.Search(id_list=[_parse_arxiv_id(arxiv_id)])
    results = list(client.results(search))

    if not results:
        raise ValueError(f"未找到 arXiv 论文: {arxiv_id}")

    paper = results[0]
    paper_id = f"arxiv_{paper.entry_id.split('/')[-1]}"

    pdf_path = None
    if download_pdf and pdf_dir:
        pdf_dir = Path(pdf_dir)
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_file = pdf_dir / f"{paper_id}.pdf"
        if not pdf_file.exists():
            _download_arxiv_pdf(paper, pdf_file)
        pdf_path = str(pdf_file.resolve())

    paper_data = {
        "id": paper_id,
        "title": paper.title.replace("\n", " ").strip(),
        "abstract": paper.summary.replace("\n", " ").strip(),
        "published_date": paper.published.date().isoformat() if paper.published else datetime.now().isoformat()[:10],
        "updated_date": paper.updated.date().isoformat() if paper.updated else datetime.now().isoformat(),
        "categories": ", ".join(paper.categories),
        "pdf_path": pdf_path,
        "source": "arxiv",
        "arxiv_url": paper.entry_id,
    }

    upsert_paper(conn, paper_data)
    _save_authors_from_arxiv(conn, paper_id, paper.authors, getattr(paper, "affiliation", None))
    conn.commit()
    conn.close()
    return paper_id


def _save_authors_from_arxiv(conn, paper_id: str, authors: list, affiliations: Optional[list] = None) -> None:
    cur = conn.cursor()
    for order, author in enumerate(authors):
        name = str(author).strip()
        affiliation = ""
        if affiliations and order < len(affiliations) and affiliations[order]:
            affiliation = str(affiliations[order]).strip()

        cur.execute("INSERT OR IGNORE INTO authors (name, affiliation) VALUES (?, ?)", (name, affiliation))
        cur.execute("SELECT id FROM authors WHERE name = ?", (name,))
        author_id = cur.fetchone()[0]

        if affiliation:
            cur.execute("INSERT OR IGNORE INTO institutions (name) VALUES (?)", (affiliation,))
            cur.execute("SELECT id FROM institutions WHERE name = ?", (affiliation,))
            inst_id = cur.fetchone()[0]
            cur.execute(
                "INSERT OR IGNORE INTO paper_institutions (paper_id, institution_id) VALUES (?, ?)",
                (paper_id, inst_id),
            )

        cur.execute(
            "INSERT OR IGNORE INTO paper_authors (paper_id, author_id, author_order) VALUES (?, ?, ?)",
            (paper_id, author_id, order),
        )


def search_arxiv(query: str, max_results: int = 10, db_path: Optional[Path] = None,
                 download_pdf: bool = False, pdf_dir: Optional[Path] = None) -> list[str]:
    """搜索 arXiv 并批量入库，返回 paper_id 列表。"""
    init_db(db_path)
    conn = get_connection(db_path)
    paper_ids = []

    client = arxiv.Client(page_size=min(max_results, 50), delay_seconds=1)
    search = arxiv.Search(query=query, max_results=max_results, sort_by=arxiv.SortCriterion.Relevance)

    for result in client.results(search):
        paper_id = f"arxiv_{result.entry_id.split('/')[-1]}"
        pdf_path = None
        if download_pdf and pdf_dir:
            pdf_dir = Path(pdf_dir)
            pdf_dir.mkdir(parents=True, exist_ok=True)
            pdf_file = pdf_dir / f"{paper_id}.pdf"
            if not pdf_file.exists():
                _download_arxiv_pdf(result, pdf_file)
            pdf_path = str(pdf_file.resolve())

        paper_data = {
            "id": paper_id,
            "title": result.title.replace("\n", " ").strip(),
            "abstract": result.summary.replace("\n", " ").strip(),
            "published_date": result.published.date().isoformat() if result.published else datetime.now().isoformat()[:10],
            "updated_date": result.updated.date().isoformat() if result.updated else datetime.now().isoformat(),
            "categories": ", ".join(result.categories),
            "pdf_path": pdf_path,
            "source": "arxiv",
            "arxiv_url": result.entry_id,
        }
        upsert_paper(conn, paper_data)
        _save_authors_from_arxiv(conn, paper_id, result.authors, getattr(result, "affiliation", None))
        paper_ids.append(paper_id)

    conn.commit()
    conn.close()
    return paper_ids


def search_arxiv_only(query: str, max_results: int = 10) -> list[dict]:
    """只搜索 arXiv，不自动入库，返回论文元数据列表。"""
    client = arxiv.Client(page_size=min(max_results, 50), delay_seconds=1)
    search = arxiv.Search(query=query, max_results=max_results, sort_by=arxiv.SortCriterion.Relevance)

    results = []
    for result in client.results(search):
        paper_id = f"arxiv_{result.entry_id.split('/')[-1]}"
        results.append({
            "id": paper_id,
            "title": result.title.replace("\n", " ").strip(),
            "abstract": result.summary.replace("\n", " ").strip(),
            "published_date": result.published.date().isoformat() if result.published else "",
            "categories": ", ".join(result.categories),
            "arxiv_url": result.entry_id,
            "authors": [str(a).strip() for a in getattr(result, "authors", [])],
        })

    return results
