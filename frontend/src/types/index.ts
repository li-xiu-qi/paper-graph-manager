export interface Paper {
  id: string;
  title: string;
  abstract: string;
  published_date: string;
  categories: string;
  source: "local" | "arxiv";
  arxiv_url?: string;
  pdf_path?: string;
  md_path?: string;
  core_contribution?: string;
  authors?: string[];
  teams?: string[];
}

export interface ArxivSearchResult {
  id: string;
  title: string;
  abstract: string;
  published_date: string;
  categories: string;
  arxiv_url: string;
  authors: string[];
}

export interface GraphNode {
  id: string;
  label?: string;
  title?: string;
  group?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  papers?: Array<{ id: string; title: string; date: string }>;
  weight?: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  papers?: Paper[];
  tool_calls?: Array<{
    tool: string;
    arguments?: Record<string, any>;
    result?: any;
    status?: "running" | "done";
  }>;
  created_at?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface NoteItem {
  paper_id: string;
  title: string;
  path?: string;
  updated_at: string;
  content?: string;
}
