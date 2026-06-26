"""Paper Graph Manager - FastAPI 后端服务。"""

import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from paper_graph.database import init_db, get_connection, list_papers, get_paper, create_chat_session, get_chat_session, list_chat_sessions, delete_chat_session, add_chat_message, get_chat_messages, update_chat_session_title
from paper_graph.ingest import ingest_local_pdf, ingest_arxiv_id, search_arxiv, search_arxiv_only, _download_arxiv_pdf
from paper_graph.annotate import annotate_paper, annotate_all, get_default_model
from paper_graph.graph import build_team_graph, build_paper_graph
from paper_graph.notes import list_notes, get_note, save_note as notes_save, create_note_template, delete_note as notes_delete
from paper_graph.chat_agent import run_agent, run_agent_stream
import arxiv
import re

# 加载 .env 文件
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

DATA_DIR = BASE_DIR.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "papers.db"

app = FastAPI(title="Paper Graph Manager API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────
# 数据模型
# ──────────────────────────────

class PaperIngestArxivRequest(BaseModel):
    arxiv_id: str
    download_pdf: bool = False


class PaperSearchRequest(BaseModel):
    query: str
    max_results: int = 10
    download_pdf: bool = False


class EnhanceRequest(BaseModel):
    paper_id: Optional[str] = None
    model: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    mode: str = "auto"  # auto | structured | rag


class ChatResponse(BaseModel):
    mode: str
    answer: str
    papers: list[dict]
    tool_calls: list[dict] = []


class BatchIngestRequest(BaseModel):
    paper_ids: list[str]
    download_pdf: bool = False


class ChatSessionCreate(BaseModel):
    title: str = ""


class ChatSessionRename(BaseModel):
    title: str


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    papers: Optional[list[dict]] = None
    tool_calls: Optional[list[dict]] = None
    created_at: str


# ──────────────────────────────
# 论文 API
# ──────────────────────────────

@app.get("/api/papers/search")
def api_search_arxiv(q: str, max_results: int = 10, download: bool = False):
    try:
        paper_ids = search_arxiv(q, max_results=max_results, db_path=DB_PATH, download_pdf=download, pdf_dir=DATA_DIR / "pdfs")
        return {"paper_ids": paper_ids}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/papers/search-arxiv")
def api_search_arxiv_only(q: str, max_results: int = 10):
    try:
        results = search_arxiv_only(q, max_results=max_results)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/papers")
def api_list_papers(source: Optional[str] = None, q: Optional[str] = None):
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        df = list_papers(DB_PATH, source=source)
        if q:
            df = df[df["title"].str.contains(q, case=False, na=False, regex=False) | df["abstract"].str.contains(q, case=False, na=False, regex=False)]
        records = df.to_dict(orient="records")
        # json.dumps 无法直接序列化 NaN，需要手动清洗
        for record in records:
            for key, value in list(record.items()):
                if isinstance(value, float) and value != value:
                    record[key] = None
        return records
    finally:
        conn.close()


@app.get("/api/papers/{paper_id}")
def api_get_paper(paper_id: str):
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        paper = get_paper(conn, paper_id)
        if not paper:
            raise HTTPException(status_code=404, detail="论文不存在")
        return paper
    finally:
        conn.close()


@app.post("/api/papers/ingest-pdf")
async def api_ingest_pdf(file: UploadFile = File(...)):
    init_db(DB_PATH)
    safe_name = os.path.basename(file.filename or "upload.pdf")
    if not safe_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件上传")
    temp_path = DATA_DIR / safe_name
    try:
        content = await file.read()
        temp_path.write_bytes(content)
        paper_id = ingest_local_pdf(temp_path, DB_PATH)
        # 自动生成 Markdown 笔记模板
        try:
            create_note_template(DB_PATH, paper_id)
        except Exception:
            pass
        return {"paper_id": paper_id, "title": file.filename}
    finally:
        if temp_path.exists():
            temp_path.unlink()


@app.post("/api/papers/ingest-arxiv")
def api_ingest_arxiv(req: PaperIngestArxivRequest):
    init_db(DB_PATH)
    try:
        paper_id = ingest_arxiv_id(req.arxiv_id, DB_PATH, download_pdf=req.download_pdf, pdf_dir=DATA_DIR / "pdfs")
        # 自动生成 Markdown 笔记模板
        try:
            create_note_template(DB_PATH, paper_id)
        except Exception:
            pass
        return {"paper_id": paper_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/papers/{paper_id}/annotate")
def api_annotate_paper(paper_id: str, req: EnhanceRequest):
    try:
        result = annotate_paper(paper_id, model=req.model)
        return result
    except Exception as e:
        error_msg = str(e)
        if "Connection error" in error_msg or "ConnectError" in error_msg or "WinError 10061" in error_msg:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "LLM 服务不可用",
                    "suggestion": "请检查 backend/.env 中的 LLM_API_KEY / LLM_BASE_URL 配置，确认模型服务已启动。",
                    "hint": "当前默认指向 http://localhost:1234/v1，若使用 Step Plan，请改为 https://api.stepfun.com/step_plan/v1",
                },
            )
        raise HTTPException(status_code=400, detail=error_msg)


@app.post("/api/papers/annotate-all")
def api_annotate_all(req: EnhanceRequest):
    count = annotate_all(model=req.model)
    return {"annotated_count": count}


@app.post("/api/papers/batch-annotate")
def api_batch_annotate(req: EnhanceRequest):
    """批量标注所有未标注论文。"""
    count = annotate_all(model=req.model)
    return {"annotated_count": count}


@app.post("/api/papers/batch-ingest")
def api_batch_ingest(req: BatchIngestRequest):
    """批量入库论文 ID 列表。"""
    results = []
    for paper_id in req.paper_ids:
        try:
            # 解析 arxiv ID
            arxiv_id = paper_id.replace("arxiv_", "")
            paper_id_new = ingest_arxiv_id(arxiv_id, DB_PATH, download_pdf=req.download_pdf, pdf_dir=DATA_DIR / "pdfs")
            results.append({"id": paper_id, "status": "success", "paper_id": paper_id_new})
        except Exception as e:
            results.append({"id": paper_id, "status": "error", "error": str(e)})
    return {"results": results}


@app.post("/api/papers/{paper_id}/download-pdf")
def api_download_pdf(paper_id: str):
    """下载论文 PDF。"""
    try:
        arxiv_id = paper_id.replace("arxiv_", "")
        client = arxiv.Client(page_size=1, delay_seconds=1)
        search = arxiv.Search(id_list=[arxiv_id])
        results = list(client.results(search))
        if not results:
            raise HTTPException(status_code=404, detail="论文不存在")

        paper = results[0]
        pdf_dir = DATA_DIR / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_file = pdf_dir / f"{paper_id}.pdf"
        if not pdf_file.exists():
            _download_arxiv_pdf(paper, pdf_file)

        # 更新数据库中的 pdf_path
        conn = get_connection(DB_PATH)
        cur = conn.cursor()
        cur.execute("UPDATE papers SET pdf_path = ? WHERE id = ?", (str(pdf_file.resolve()), paper_id))
        conn.commit()
        conn.close()

        return {"status": "success", "pdf_path": str(pdf_file.resolve())}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────
# 图谱 API
# ──────────────────────────────

@app.get("/api/graph/team")
def api_graph_team():
    init_db(DB_PATH)
    graph = build_team_graph(DB_PATH)
    return {
        "nodes": [{"id": n, **graph.nodes[n]} for n in graph.nodes()],
        "edges": [{"source": u, "target": v, **graph.edges[u, v]} for u, v in graph.edges()],
    }


@app.get("/api/graph/paper")
def api_graph_paper():
    init_db(DB_PATH)
    graph = build_paper_graph(DB_PATH)
    return {
        "nodes": [{"id": n, **graph.nodes[n]} for n in graph.nodes()],
        "edges": [{"source": u, "target": v, **graph.edges[u, v]} for u, v in graph.edges()],
    }


# ──────────────────────────────
# 聊天 API（混合模式 + 会话管理 + 流式）
# ──────────────────────────────


def _derive_session_title(message: str) -> str:
    """根据用户第一条消息生成会话标题（前 10 个字，不足取全部）。"""
    text = message.strip().replace("\n", " ").replace("\r", "")
    if not text:
        return "未命名会话"
    return text[:10]


@app.get("/api/chat/sessions")
def api_list_chat_sessions():
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        sessions = list_chat_sessions(conn)
        return sessions
    finally:
        conn.close()


@app.post("/api/chat/sessions", response_model=ChatSessionResponse)
def api_create_chat_session(req: ChatSessionCreate):
    init_db(DB_PATH)
    session_id = f"session_{int(__import__('time').time() * 1000)}"
    conn = get_connection(DB_PATH)
    try:
        create_chat_session(conn, session_id, req.title)
        session = get_chat_session(conn, session_id)
        return session
    finally:
        conn.close()


@app.delete("/api/chat/sessions/{session_id}")
def api_delete_chat_session(session_id: str):
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        delete_chat_session(conn, session_id)
        return {"status": "deleted"}
    finally:
        conn.close()


@app.patch("/api/chat/sessions/{session_id}", response_model=ChatSessionResponse)
def api_rename_chat_session(session_id: str, req: ChatSessionRename):
    """重命名会话。"""
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        update_chat_session_title(conn, session_id, req.title.strip())
        session = get_chat_session(conn, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        return session
    finally:
        conn.close()


@app.get("/api/chat/sessions/{session_id}/messages")
def api_get_chat_messages(session_id: str):
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        messages = get_chat_messages(conn, session_id)
        return messages
    finally:
        conn.close()


@app.post("/api/chat/sessions/{session_id}/messages", response_model=ChatResponse)
def api_chat_session_message(session_id: str, req: ChatRequest):
    """会话内发送消息（非流式）。"""
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        create_chat_session(conn, session_id)
        session = get_chat_session(conn, session_id)
        if not session.get("title"):
            update_chat_session_title(conn, session_id, _derive_session_title(req.message))
        add_chat_message(conn, f"msg_{int(__import__('time').time() * 1000)}_{req.message[:8]}", session_id, "user", req.message)
    finally:
        conn.close()

    # 读取历史消息给 Agent 做上下文
    conn = get_connection(DB_PATH)
    try:
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in get_chat_messages(conn, session_id)
        ]
    finally:
        conn.close()

    response = _chat_generate(req.message, history=history)

    conn = get_connection(DB_PATH)
    try:
        add_chat_message(
            conn,
            f"msg_{int(__import__('time').time() * 1000)}_assistant",
            session_id,
            "assistant",
            response.answer,
            json.dumps(response.papers, ensure_ascii=False, default=str),
            json.dumps(response.tool_calls, ensure_ascii=False, default=str),
        )
    finally:
        conn.close()

    return response


@app.post("/api/chat/sessions/{session_id}/messages/stream")
async def api_chat_session_stream(session_id: str, req: ChatRequest):
    """会话内发送消息（流式输出）。"""
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        create_chat_session(conn, session_id)
        session = get_chat_session(conn, session_id)
        if not session.get("title"):
            update_chat_session_title(conn, session_id, _derive_session_title(req.message))
        add_chat_message(conn, f"msg_{int(__import__('time').time() * 1000)}_{req.message[:8]}", session_id, "user", req.message)
    finally:
        conn.close()

    # 读取历史消息
    conn = get_connection(DB_PATH)
    try:
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in get_chat_messages(conn, session_id)
        ]
    finally:
        conn.close()

    async def generate():
        answer = ""
        papers: list[dict] = []
        tool_calls: list[dict] = []

        async for event in run_agent_stream(req.message, history=history):
            yield event
            # 解析最终答案以便落库
            data = json.loads(event.replace("data: ", ""))
            if data.get("type") == "answer":
                answer = data.get("content", "")
                papers = data.get("papers", [])
                tool_calls = data.get("tool_calls", [])

        conn = get_connection(DB_PATH)
        try:
            add_chat_message(
                conn,
                f"msg_{int(__import__('time').time() * 1000)}_assistant",
                session_id,
                "assistant",
                answer,
                json.dumps(papers, ensure_ascii=False, default=str),
                json.dumps(tool_calls, ensure_ascii=False, default=str),
            )
        finally:
            conn.close()

    from fastapi.responses import StreamingResponse
    return StreamingResponse(generate(), media_type="text/event-stream; charset=utf-8")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/health")
def health_legacy():
    llm_configured = bool(os.getenv("LLM_API_KEY") and os.getenv("LLM_BASE_URL"))
    return {
        "status": "ok",
        "llm_configured": llm_configured,
        "model": os.getenv("LLM_MODEL", "step-3.7-flash"),
    }


def _cleanup_logs(max_mb: int = 5) -> None:
    """启动时清理过大的 server.log，避免无限增长。"""
    log_path = BASE_DIR / "server.log"
    if not log_path.exists():
        return
    size_mb = log_path.stat().st_size / (1024 * 1024)
    if size_mb > max_mb:
        log_path.write_text("", encoding="utf-8")


_cleanup_logs()


# ──────────────────────────────
# 笔记 API
# ──────────────────────────────

@app.get("/api/notes")
def api_list_notes():
    init_db(DB_PATH)
    result = list_notes(DB_PATH)
    return result


@app.get("/api/notes/{paper_id}")
def api_get_note(paper_id: str):
    init_db(DB_PATH)
    result = get_note(DB_PATH, paper_id)
    if not result:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return result


@app.post("/api/notes/{paper_id}")
def api_save_note(paper_id: str, req: dict):
    init_db(DB_PATH)
    content = req.get("content", "")
    result = notes_save(DB_PATH, paper_id, content)
    return result


@app.post("/api/notes/{paper_id}/template")
def api_create_note_template(paper_id: str):
    init_db(DB_PATH)
    result = create_note_template(DB_PATH, paper_id)
    return result


@app.delete("/api/notes/{paper_id}")
def api_delete_note(paper_id: str):
    init_db(DB_PATH)
    result = notes_delete(DB_PATH, paper_id)
    return result
