import type { Paper, NoteItem, ChatMessage, ChatSession } from "@/types";

const API_BASE = "/api";

export async function fetchPapers(source?: string, q?: string): Promise<Paper[]> {
  const params = new URLSearchParams();
  if (source) params.set("source", source);
  if (q) params.set("q", q);
  const query = params.toString();
  const res = await fetch(`${API_BASE}/papers${query ? `?${query}` : ""}`);
  if (!res.ok) throw new Error("Failed to fetch papers");
  return res.json();
}

export async function fetchPaper(id: string): Promise<Paper> {
  const res = await fetch(`${API_BASE}/papers/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error("Failed to fetch paper");
  return res.json();
}

export async function ingestPdf(file: File): Promise<{ paper_id: string; title: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/papers/ingest-pdf`, { method: "POST", body: form });
  if (!res.ok) throw new Error("Failed to ingest PDF");
  return res.json();
}

export async function ingestArxiv(arxivId: string, downloadPdf = false) {
  const res = await fetch(`${API_BASE}/papers/ingest-arxiv`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ arxiv_id: arxivId, download_pdf: downloadPdf }),
  });
  if (!res.ok) throw new Error("Failed to ingest arXiv");
  return res.json();
}

export async function searchArxiv(query: string, maxResults = 10, download = false) {
  const res = await fetch(`${API_BASE}/papers/search?${new URLSearchParams({ q: query, max_results: String(maxResults), download: String(download) })}`);
  if (!res.ok) throw new Error("Failed to search arXiv");
  return res.json();
}

export async function searchArxivResults(query: string, maxResults = 10) {
  const res = await fetch(`${API_BASE}/papers/search-arxiv?${new URLSearchParams({ q: query, max_results: String(maxResults) })}`);
  if (!res.ok) throw new Error("Failed to search arXiv");
  return res.json();
}

export async function annotatePaper(paperId: string, model = "gpt-4o-mini") {
  const res = await fetch(`${API_BASE}/papers/${encodeURIComponent(paperId)}/annotate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paper_id: paperId, model }),
  });
  if (!res.ok) throw new Error("Failed to annotate paper");
  return res.json();
}

export async function fetchGraphTeam() {
  const res = await fetch(`${API_BASE}/graph/team`);
  if (!res.ok) throw new Error("Failed to fetch team graph");
  return res.json();
}

export async function fetchGraphPaper() {
  const res = await fetch(`${API_BASE}/graph/paper`);
  if (!res.ok) throw new Error("Failed to fetch paper graph");
  return res.json();
}

export async function listChatSessions(): Promise<ChatSession[]> {
  const res = await fetch(`${API_BASE}/chat/sessions`);
  if (!res.ok) throw new Error("Failed to list chat sessions");
  return res.json();
}

export async function createChatSession(title = ""): Promise<ChatSession> {
  const res = await fetch(`${API_BASE}/chat/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error("Failed to create chat session");
  return res.json();
}

export async function deleteChatSession(sessionId: string) {
  const res = await fetch(`${API_BASE}/chat/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete chat session");
  return res.json();
}

export async function renameChatSession(sessionId: string, title: string): Promise<ChatSession> {
  const res = await fetch(`${API_BASE}/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error("Failed to rename chat session");
  return res.json();
}

export async function getChatMessages(sessionId: string): Promise<ChatMessage[]> {
  const res = await fetch(`${API_BASE}/chat/sessions/${encodeURIComponent(sessionId)}/messages`);
  if (!res.ok) throw new Error("Failed to get chat messages");
  return res.json();
}

export async function sendChatMessage(sessionId: string, message: string, mode = "auto"): Promise<ChatMessage> {
  const res = await fetch(`${API_BASE}/chat/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, mode }),
  });
  if (!res.ok) throw new Error("Failed to send chat message");
  return res.json();
}

export interface ChatStreamEvent {
  type: "thinking" | "tool_call" | "tool_result" | "answer";
  content?: string;
  tool?: string;
  arguments?: Record<string, unknown>;
  result?: Record<string, unknown>;
  papers?: any[];
  tool_calls?: any[];
}

export async function streamChatMessage(
  sessionId: string,
  message: string,
  onEvent: (event: ChatStreamEvent) => void,
  onComplete: (fullMessage: ChatMessage) => void,
  onError: (err: Error) => void
) {
  try {
    const res = await fetch(`${API_BASE}/chat/sessions/${encodeURIComponent(sessionId)}/messages/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, mode: "auto" }),
    });

    if (!res.ok) throw new Error("Failed to stream chat message");

    const reader = res.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let buffer = "";
    let fullText = "";
    let finalPapers: any[] = [];
    let finalToolCalls: any[] = [];

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data: ")) continue;

        const dataStr = trimmed.slice(6);
        if (dataStr === "[DONE]") continue;

        try {
          const event = JSON.parse(dataStr) as ChatStreamEvent;
          onEvent(event);

          if (event.type === "answer") {
            fullText = event.content || "";
            finalPapers = event.papers || [];
            finalToolCalls = event.tool_calls || [];
          }
        } catch {
          // ignore parse error
        }
      }
    }

    onComplete({
      role: "assistant",
      content: fullText,
      papers: finalPapers as any,
      tool_calls: finalToolCalls as any,
      created_at: new Date().toISOString(),
    });
  } catch (err) {
    onError(err instanceof Error ? err : new Error(String(err)));
  }
}

export async function batchIngest(paperIds: string[], downloadPdf = false) {
  const res = await fetch(`${API_BASE}/papers/batch-ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paper_ids: paperIds, download_pdf: downloadPdf }),
  });
  if (!res.ok) throw new Error("Failed to batch ingest");
  return res.json();
}

export async function downloadPdf(paperId: string) {
  const res = await fetch(`${API_BASE}/papers/${encodeURIComponent(paperId)}/download-pdf`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to download PDF");
  return res.json();
}

export async function batchAnnotate(model = "gpt-4o-mini") {
  const res = await fetch(`${API_BASE}/papers/batch-annotate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
  if (!res.ok) throw new Error("Failed to batch annotate");
  return res.json();
}

export async function listNotes(): Promise<NoteItem[]> {
  const res = await fetch(`${API_BASE}/notes`);
  if (!res.ok) throw new Error("Failed to list notes");
  return res.json();
}

export async function getNote(paperId: string): Promise<NoteItem> {
  const res = await fetch(`${API_BASE}/notes/${encodeURIComponent(paperId)}`);
  if (!res.ok) throw new Error("Failed to get note");
  return res.json();
}

export async function saveNote(paperId: string, content: string): Promise<{ success: boolean }> {
  const res = await fetch(`${API_BASE}/notes/${encodeURIComponent(paperId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error("Failed to save note");
  return res.json();
}

export async function createNoteTemplate(paperId: string): Promise<{ success: boolean }> {
  const res = await fetch(`${API_BASE}/notes/${encodeURIComponent(paperId)}/template`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to create note template");
  return res.json();
}

export async function deleteNote(paperId: string): Promise<{ success: boolean }> {
  const res = await fetch(`${API_BASE}/notes/${encodeURIComponent(paperId)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete note");
  return res.json();
}
