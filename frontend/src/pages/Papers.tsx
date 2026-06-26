import { Skeleton } from "@/components/ui/skeleton";
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  fetchPapers,
  ingestPdf,
  ingestArxiv,
  searchArxivResults,
  annotatePaper,
  downloadPdf,
  batchAnnotate,
} from "@/services/api";
import type { Paper, ArxivSearchResult } from "@/types";
import {
  Upload,
  Search,
  Sparkles,
  Download,
  FileText,
  CheckCircle2,
  AlertCircle,
  Library,
  Plus,
} from "lucide-react";
import { ErrorAlert } from "@/components/ErrorAlert";

function StatusBadge({
  annotated,
  hasPdf,
  hasNotes,
}: {
  annotated: boolean;
  hasPdf: boolean;
  hasNotes: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {annotated ? (
        <Badge
          variant="default"
          className="gap-0.5 bg-indigo-600 px-1.5 py-0.5 text-[10px] text-white hover:bg-indigo-700 dark:bg-indigo-600 dark:hover:bg-indigo-500"
        >
          <CheckCircle2 className="h-2.5 w-2.5" />
          已标注
        </Badge>
      ) : (
        <Badge variant="outline" className="gap-0.5 px-1.5 py-0.5 text-[10px] text-muted-foreground">
          <AlertCircle className="h-2.5 w-2.5" />
          未标注
        </Badge>
      )}
      {hasPdf && (
        <Badge variant="secondary" className="px-1.5 py-0.5 text-[10px]">
          PDF
        </Badge>
      )}
      {hasNotes && (
        <Badge variant="secondary" className="px-1.5 py-0.5 text-[10px]">
          笔记
        </Badge>
      )}
    </div>
  );
}

function EmptyState({ filter, onAdd }: { filter: boolean; onAdd: () => void }) {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center justify-center py-12 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted">
          <Library className="h-6 w-6 text-muted-foreground" />
        </div>
        <h3 className="mt-4 text-base font-semibold">
          {filter ? "未找到匹配的论文" : "知识库还是空的"}
        </h3>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          {filter
            ? "尝试更换搜索关键词，或清空筛选条件。"
            : "从 arXiv 搜索论文或上传本地 PDF，开始构建你的论文图谱。"}
        </p>
        {!filter && (
          <Button className="mt-5 gap-2" size="sm" onClick={onAdd}>
            <Plus className="h-4 w-4" />
            添加第一篇论文
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

export function Papers() {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);
  const [localFilter, setLocalFilter] = useState("");
  const [arxivId, setArxivId] = useState("");
  const [arxivSearchKeyword, setArxivSearchKeyword] = useState("");
  const [searchResults, setSearchResults] = useState<ArxivSearchResult[]>([]);
  const [ingesting, setIngesting] = useState<Record<string, boolean>>({});
  const [downloading, setDownloading] = useState<Record<string, boolean>>({});
  const [annotating, setAnnotating] = useState<Record<string, boolean>>({});
  const [batchLoading, setBatchLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [pageError, setPageError] = useState<{
    message: string;
    suggestion?: string;
    onRetry?: () => void;
  } | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchPapers()
      .then((data) => {
        setPapers(data);
        setLoading(false);
      })
      .catch((err) => {
        setPageError({
          message: "加载论文列表失败",
          suggestion: err instanceof Error ? err.message : String(err),
          onRetry: () => window.location.reload(),
        });
        setLoading(false);
      });
  }, []);

  const showToast = (message: string) => {
    setToast(message);
    setTimeout(() => setToast(null), 3000);
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await ingestPdf(file);
      const updated = await fetchPapers();
      setPapers(updated);
      showToast("PDF 上传成功");
    } catch (err) {
      showToast("上传失败: " + err);
    }
  };

  const handleIngestArxiv = async () => {
    if (!arxivId.trim()) return;
    try {
      await ingestArxiv(arxivId.trim());
      setArxivId("");
      const updated = await fetchPapers();
      setPapers(updated);
      showToast("arXiv 入库成功");
    } catch (err) {
      showToast("入库失败: " + err);
    }
  };

  const handleSearch = async () => {
    if (!arxivSearchKeyword.trim()) return;
    try {
      const result = await searchArxivResults(arxivSearchKeyword.trim(), 10);
      setSearchResults(result.results || []);
    } catch (err) {
      showToast("搜索失败: " + err);
    }
  };

  const handleIngestResult = async (result: ArxivSearchResult) => {
    setIngesting((prev) => ({ ...prev, [result.id]: true }));
    try {
      await ingestArxiv(result.id);
      const updated = await fetchPapers();
      setPapers(updated);
      setSearchResults((prev) => prev.filter((r) => r.id !== result.id));
      showToast("入库成功");
    } catch (err) {
      showToast("入库失败: " + err);
    } finally {
      setIngesting((prev) => ({ ...prev, [result.id]: false }));
    }
  };

  const handleAnnotate = async (id: string) => {
    setAnnotating((prev) => ({ ...prev, [id]: true }));
    try {
      await annotatePaper(id);
      showToast("智能标注完成");
      const updated = await fetchPapers();
      setPapers(updated);
    } catch (err) {
      showToast("智能标注失败: " + err);
    } finally {
      setAnnotating((prev) => ({ ...prev, [id]: false }));
    }
  };

  const handleBatchAnnotate = async () => {
    setBatchLoading(true);
    try {
      const result = await batchAnnotate();
      showToast(`批量标注完成，共 ${result.annotated_count} 篇`);
      const updated = await fetchPapers();
      setPapers(updated);
    } catch (err) {
      showToast("批量标注失败: " + err);
    } finally {
      setBatchLoading(false);
    }
  };

  const handleDownloadPdf = async (id: string) => {
    setDownloading((prev) => ({ ...prev, [id]: true }));
    try {
      await downloadPdf(id);
      const updated = await fetchPapers();
      setPapers(updated);
      showToast("PDF 下载成功");
    } catch (err) {
      showToast("下载失败: " + err);
    } finally {
      setDownloading((prev) => ({ ...prev, [id]: false }));
    }
  };

  const pendingAnnotate = papers.filter((p) => !p.core_contribution).length;
  const withNotes = papers.filter((p) => p.md_path).length;
  const withPdf = papers.filter((p) => p.pdf_path).length;

  const filtered = papers.filter(
    (p) =>
      p.title.toLowerCase().includes(localFilter.toLowerCase()) ||
      p.abstract.toLowerCase().includes(localFilter.toLowerCase())
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">论文管理</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">入库、搜索和管理你的论文</p>
      </div>

      {pageError && (
        <ErrorAlert
          title="加载失败"
          message={pageError.message}
          suggestion={pageError.suggestion}
          onRetry={pageError.onRetry}
        />
      )}

      {toast && (
        <div className="fixed right-3 top-20 z-50 flex items-center gap-2 rounded-lg border border-border/60 bg-card px-3 py-2 text-sm shadow-lg">
          <Sparkles className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
          {toast}
        </div>
      )}

      {/* Ingest Section */}
      <div className="grid gap-3 md:grid-cols-2">
        <Card className="border-border/60">
          <CardContent className="space-y-3 p-4">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-950/40 dark:text-indigo-400">
                <Upload className="h-3.5 w-3.5" />
              </div>
              <h3 className="text-sm font-semibold">上传本地 PDF</h3>
            </div>
            <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-border bg-muted/20 py-6 transition-colors hover:border-indigo-300 hover:bg-indigo-50/30 active:scale-[0.99] dark:hover:border-indigo-800 dark:hover:bg-indigo-950/20">
              <Upload className="mb-1.5 h-6 w-6 text-muted-foreground" />
              <p className="text-xs text-muted-foreground">点击上传 PDF</p>
              <input type="file" accept=".pdf" className="hidden" onChange={handleUpload} />
            </label>
          </CardContent>
        </Card>

        <Card className="border-border/60">
          <CardContent className="space-y-3 p-4">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-950/40 dark:text-indigo-400">
                <Plus className="h-3.5 w-3.5" />
              </div>
              <h3 className="text-sm font-semibold">arXiv 入库</h3>
            </div>
            <div className="flex gap-2">
              <Input
                placeholder="输入 arXiv ID，如 2402.09199"
                value={arxivId}
                onChange={(e) => setArxivId(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleIngestArxiv()}
                className="h-9 text-sm"
              />
              <Button size="sm" onClick={handleIngestArxiv}>
                入库
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Search */}
      <Card className="border-border/60">
        <CardContent className="flex gap-2 p-3">
          <Input
            placeholder="搜索 arXiv 论文..."
            value={arxivSearchKeyword}
            onChange={(e) => setArxivSearchKeyword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            className="h-9 text-sm"
          />
          <Button onClick={handleSearch} variant="secondary" size="sm">
            <Search className="mr-1.5 h-4 w-4" />
            搜索
          </Button>
        </CardContent>
      </Card>

      {/* Search Results */}
      {searchResults.length > 0 && (
        <div className="space-y-2">
          <div>
            <h3 className="text-base font-semibold">arXiv 搜索结果</h3>
            <p className="text-xs text-muted-foreground">点击「入库」将论文添加到本地知识库</p>
          </div>
          <Card className="border-border/60">
            <CardContent className="space-y-2 p-3">
              {searchResults.map((result) => (
                <div
                  key={result.id}
                  className="flex flex-col gap-2 rounded-lg border border-border/60 p-3 sm:flex-row sm:items-start sm:justify-between"
                >
                  <div className="flex-1">
                    <h4 className="text-sm font-medium line-clamp-2">{result.title}</h4>
                    <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                      {result.abstract}
                    </p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                      <span>{result.published_date}</span>
                      <span>·</span>
                      <span>{result.categories}</span>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    className="shrink-0 self-start"
                    onClick={() => handleIngestResult(result)}
                    disabled={ingesting[result.id]}
                  >
                    {ingesting[result.id] ? "入库中..." : "入库"}
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Library List */}
      <div className="space-y-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              placeholder="筛选已入库论文..."
              value={localFilter}
              onChange={(e) => setLocalFilter(e.target.value)}
              className="h-9 max-w-sm text-sm"
            />
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
              <span>共 {papers.length} 篇</span>
              <span>·</span>
              <span>待标注 {pendingAnnotate}</span>
              <span>·</span>
              <span>有笔记 {withNotes}</span>
              <span>·</span>
              <span>有 PDF {withPdf}</span>
            </div>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleBatchAnnotate}
            disabled={batchLoading || pendingAnnotate === 0}
            className="gap-1 self-start"
          >
            <Sparkles className="h-3.5 w-3.5" />
            {batchLoading ? "标注中..." : `批量标注 (${pendingAnnotate})`}
          </Button>
        </div>

        {loading ? (
          <div className="grid gap-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Card key={i} className="border-border/60">
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 space-y-2">
                      <Skeleton className="h-4 w-3/4" />
                      <Skeleton className="h-3 w-full" />
                      <Skeleton className="h-3 w-2/3" />
                    </div>
                    <div className="hidden flex-col gap-2 sm:flex">
                      <Skeleton className="h-7 w-20" />
                      <Skeleton className="h-7 w-20" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            filter={Boolean(localFilter)}
            onAdd={() => {
              const input = document.querySelector('input[placeholder="输入 arXiv ID，如 2402.09199"]');
              (input as HTMLElement)?.focus();
            }}
          />
        ) : (
          <div className="grid gap-3">
            {filtered.map((paper) => (
              <Card
                key={paper.id}
                className="cursor-pointer border-border/60 transition-colors hover:bg-muted/50"
                onClick={() => navigate(`/papers/${paper.id}`)}
              >
                <CardContent className="p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0 flex-1">
                      <h3 className="text-sm font-medium line-clamp-2">{paper.title}</h3>
                      <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                        {paper.abstract}
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
                        <StatusBadge
                          annotated={Boolean(paper.core_contribution)}
                          hasPdf={Boolean(paper.pdf_path)}
                          hasNotes={Boolean(paper.md_path)}
                        />
                        <span className="hidden sm:inline">·</span>
                        <span className="capitalize">{paper.source}</span>
                        <span>·</span>
                        <span>{paper.published_date}</span>
                      </div>
                    </div>
                    <div
                      className="flex flex-wrap gap-2 lg:flex-col lg:items-stretch xl:flex-row"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {!paper.pdf_path && paper.source === "arxiv" && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-8 text-xs"
                          onClick={() => handleDownloadPdf(paper.id)}
                          disabled={downloading[paper.id]}
                        >
                          <Download className="mr-1 h-3.5 w-3.5" />
                          {downloading[paper.id] ? "下载中..." : "下载 PDF"}
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant={paper.core_contribution ? "outline" : "default"}
                        className="h-8 text-xs"
                        onClick={() => handleAnnotate(paper.id)}
                        disabled={annotating[paper.id]}
                      >
                        <Sparkles className="mr-1 h-3.5 w-3.5" />
                        {annotating[paper.id] ? "标注中..." : "智能标注"}
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
