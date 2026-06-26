"""论文图谱管理工具 - 智能标注模块。"""

import json
import os
from pathlib import Path
from typing import Optional

from openai import OpenAI

from .database import get_connection, get_paper, list_papers


# ──────────────────────────────
# LLM 客户端
# ──────────────────────────────

def get_client(api_key: Optional[str] = None, base_url: Optional[str] = None) -> OpenAI:
    """获取 OpenAI 兼容客户端。优先使用传入参数，否则读取环境变量。"""
    api_key = api_key or os.getenv("LLM_API_KEY", "dummy")
    base_url = base_url or os.getenv("LLM_BASE_URL", "https://api.stepfun.com/step_plan/v1")
    return OpenAI(api_key=api_key, base_url=base_url)


def get_default_model() -> str:
    """获取默认模型名称。"""
    return os.getenv("LLM_MODEL", "step-3.7-flash")


ANNOTATE_PROMPT = """你是一位学术研究助手。给定以下论文信息，请完成两项任务：

1. 用一句话提炼「核心贡献」，控制在 20 字以内，突出本文区别于其他工作的创新点。
2. 从作者和机构信息中识别研究团队，返回 JSON 格式。

论文标题：{title}
摘要：{abstract}
作者：{authors}
机构：{institutions}

请严格按以下 JSON 格式返回（不要有其他文字）：
{{
  "core_contribution": "一句话核心贡献",
  "teams": [
    {{
      "name": "团队名称（如：中科院计算所曹娟团队）",
      "institution": "主要所属机构",
      "members": ["作者名1", "作者名2"]
    }}
  ]
}}"""


# ──────────────────────────────
# 单篇标注
# ──────────────────────────────

def annotate_paper(paper_id: str, model: Optional[str] = None,
                   api_key: Optional[str] = None, base_url: Optional[str] = None) -> dict:
    """对单篇论文执行智能标注：核心贡献提炼 + 团队识别。"""
    model = model or get_default_model()
    conn = get_connection()
    paper = get_paper(conn, paper_id)
    if not paper:
        raise ValueError(f"论文不存在: {paper_id}")

    # 收集作者和机构信息
    cur = conn.cursor()
    cur.execute("""
        SELECT a.name, a.affiliation
        FROM paper_authors pa
        JOIN authors a ON pa.author_id = a.id
        WHERE pa.paper_id = ?
        ORDER BY pa.author_order
    """, (paper_id,))
    author_rows = cur.fetchall()
    authors = [r["name"] for r in author_rows]
    institutions = [r["affiliation"] for r in author_rows if r["affiliation"]]
    conn.close()

    authors_str = ", ".join(authors) if authors else "未知"
    institutions_str = ", ".join(set(institutions)) if institutions else "未知"

    prompt = ANNOTATE_PROMPT.format(
        title=paper["title"],
        abstract=paper["abstract"][:3000],
        authors=authors_str,
        institutions=institutions_str,
    )

    client = get_client(api_key, base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content.strip()

    # 清理可能的 markdown 代码块标记
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    result = json.loads(content)

    # 写回数据库
    conn = get_connection()
    cur = conn.cursor()
    from datetime import datetime
    cur.execute(
        "UPDATE papers SET core_contribution = ?, enhanced_at = ? WHERE id = ?",
        (result.get("core_contribution", ""), datetime.now().isoformat(), paper_id),
    )

    # 写入团队
    for team in result.get("teams", []):
        team_name = team.get("name", "")
        if not team_name:
            continue
        cur.execute("INSERT OR IGNORE INTO teams (name) VALUES (?)", (team_name,))
        cur.execute("SELECT id FROM teams WHERE name = ?", (team_name,))
        team_id = cur.fetchone()[0]

        for member_name in team.get("members", []):
            cur.execute("INSERT OR IGNORE INTO authors (name) VALUES (?)", (member_name,))
            cur.execute("SELECT id FROM authors WHERE name = ?", (member_name,))
            author_id = cur.fetchone()[0]
            cur.execute(
                "INSERT OR IGNORE INTO team_members (team_id, author_id) VALUES (?, ?)",
                (team_id, author_id),
            )
            cur.execute(
                "INSERT OR IGNORE INTO paper_teams (paper_id, team_id) VALUES (?, ?)",
                (paper_id, team_id),
            )

    conn.commit()
    conn.close()
    return result


def annotate_all(model: str = "step-3.7-flash", api_key: Optional[str] = None,
                 base_url: Optional[str] = None, db_path: Optional[Path] = None) -> int:
    """批量标注所有未标注的论文。"""
    conn = get_connection(db_path)
    df = list_papers(db_path)
    # 只标注没有 core_contribution 的论文
    pending = df[df["core_contribution"].isna() | (df["core_contribution"] == "")]
    count = 0

    for _, row in pending.iterrows():
        try:
            annotate_paper(row["id"], model=model, api_key=api_key, base_url=base_url)
            count += 1
        except Exception as e:
            print(f"标注失败 {row['id']}: {e}")

    conn.close()
    return count
