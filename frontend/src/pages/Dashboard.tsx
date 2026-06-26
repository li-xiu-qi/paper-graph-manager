import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchPapers } from "@/services/api";
import type { Paper } from "@/types";
import { ErrorAlert } from "@/components/ErrorAlert";
import {
  Library,
  Sparkles,
  BookOpen,
  FileText,
  TrendingUp,
  ArrowRight,
  Zap,
  Network,
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

const STAT_CARDS = [
  {
    key: "total" as const,
    label: "总论文数",
    icon: Library,
  },
  {
    key: "annotated" as const,
    label: "已标注",
    icon: Sparkles,
  },
  {
    key: "withNotes" as const,
    label: "有笔记",
    icon: BookOpen,
  },
  {
    key: "withPdf" as const,
    label: "有 PDF",
    icon: FileText,
  },
];

function StatCard({
  label,
  value,
  icon: Icon,
  onClick,
  children,
}: {
  label: string;
  value: number;
  icon: React.ElementType;
  onClick: () => void;
  children?: React.ReactNode;
}) {
  return (
    <Card
      className="group cursor-pointer border-border/60 bg-card transition-all duration-200 hover:shadow-md"
      onClick={onClick}
    >
      <CardContent className="flex items-center gap-4 p-4 sm:p-5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 transition-colors group-hover:bg-indigo-100 dark:bg-indigo-950/40 dark:text-indigo-400 dark:group-hover:bg-indigo-950/60">
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="text-2xl font-semibold tracking-tight">{value}</p>
          {children}
        </div>
      </CardContent>
    </Card>
  );
}

function EmptyState({ onAction }: { onAction: () => void }) {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center justify-center py-12 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted">
          <Library className="h-6 w-6 text-muted-foreground" />
        </div>
        <h3 className="mt-4 text-base font-semibold">知识库还是空的</h3>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          从 arXiv 搜索论文或上传本地 PDF，开始构建你的论文图谱。
        </p>
        <Button className="mt-5 gap-2" size="sm" onClick={onAction}>
          <Zap className="h-4 w-4" />
          添加第一篇论文
        </Button>
      </CardContent>
    </Card>
  );
}

export function Dashboard() {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);
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
          message: "加载仪表盘数据失败",
          suggestion: err instanceof Error ? err.message : String(err),
          onRetry: () => window.location.reload(),
        });
        setLoading(false);
      });
  }, []);

  const stats = {
    total: papers.length,
    arxiv: papers.filter((p) => p.source === "arxiv").length,
    local: papers.filter((p) => p.source === "local").length,
    annotated: papers.filter((p) => p.core_contribution).length,
    pending: papers.filter((p) => !p.core_contribution).length,
    withNotes: papers.filter((p) => p.md_path).length,
    withPdf: papers.filter((p) => p.pdf_path).length,
  };

  const annotationRate =
    stats.total > 0 ? Math.round((stats.annotated / stats.total) * 100) : 0;
  const notesRate =
    stats.total > 0 ? Math.round((stats.withNotes / stats.total) * 100) : 0;
  const pdfRate =
    stats.total > 0 ? Math.round((stats.withPdf / stats.total) * 100) : 0;

  const recent = papers.slice(0, 5);

  return (
    <div className="space-y-5">
      {/* Hero Header */}
      <div className="relative overflow-hidden rounded-2xl border border-border/60 bg-card p-4 sm:p-5">
        <div className="absolute -right-12 -top-12 h-48 w-48 rounded-full bg-indigo-500/5 blur-3xl" />
        <div className="relative flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
              欢迎回来
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              管理论文、构建知识图谱、与 AI 聊聊研究进展。
            </p>
          </div>
          {stats.total > 0 && (
            <div className="flex items-center gap-2 self-start rounded-full bg-muted/60 px-3 py-1.5 text-xs text-muted-foreground">
              <Zap className="h-3.5 w-3.5 text-indigo-500" />
              <span>已收录 {stats.total} 篇论文</span>
            </div>
          )}
        </div>
      </div>

      {pageError && (
        <ErrorAlert
          title="加载失败"
          message={pageError.message}
          suggestion={pageError.suggestion}
          onRetry={pageError.onRetry}
        />
      )}

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="border-border/60">
              <CardContent className="p-4 sm:p-5">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="mt-2 h-8 w-16" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : stats.total === 0 ? (
        <EmptyState onAction={() => navigate("/papers")} />
      ) : (
        <>
          {/* Stats Grid */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="总论文数"
              value={stats.total}
              icon={Library}
              onClick={() => navigate("/papers")}
            />
            <StatCard
              label="已标注"
              value={stats.annotated}
              icon={Sparkles}
              onClick={() => navigate("/papers")}
            >
              <div className="mt-1.5">
                <div className="mb-1 flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>标注率</span>
                  <span className="font-medium text-foreground">{annotationRate}%</span>
                </div>
                <div className="h-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-indigo-600 transition-all duration-500 dark:bg-indigo-500"
                    style={{ width: `${annotationRate}%` }}
                  />
                </div>
              </div>
            </StatCard>
            <StatCard
              label="有笔记"
              value={stats.withNotes}
              icon={BookOpen}
              onClick={() => navigate("/notes")}
            >
              <p className="mt-1 text-[11px] text-muted-foreground">覆盖率 {notesRate}%</p>
            </StatCard>
            <StatCard
              label="有 PDF"
              value={stats.withPdf}
              icon={FileText}
              onClick={() => navigate("/papers")}
            >
              <p className="mt-1 text-[11px] text-muted-foreground">覆盖率 {pdfRate}%</p>
            </StatCard>
          </div>

          {/* Main Content Grid */}
          <div className="grid gap-4 lg:grid-cols-3">
            {/* Library Health */}
            <Card className="border-border/60 lg:col-span-1">
              <CardHeader className="pb-2 pt-4">
                <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                  <TrendingUp className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
                  知识库健康度
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 pb-4">
                <div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">论文标注率</span>
                    <span className="font-medium text-foreground">{annotationRate}%</span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-indigo-600 transition-all duration-700 dark:bg-indigo-500"
                      style={{ width: `${annotationRate}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">笔记覆盖率</span>
                    <span className="font-medium text-foreground">{notesRate}%</span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-slate-400 transition-all duration-700 dark:bg-slate-500"
                      style={{ width: `${notesRate}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">PDF 完整率</span>
                    <span className="font-medium text-foreground">{pdfRate}%</span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-slate-300 transition-all duration-700 dark:bg-slate-600"
                      style={{ width: `${pdfRate}%` }}
                    />
                  </div>
                </div>

                <div className="rounded-xl bg-muted/50 p-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-950/40 dark:text-indigo-400">
                      <Sparkles className="h-4 w-4" />
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">待标注论文</p>
                      <p className="text-xl font-semibold">{stats.pending}</p>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Recent Papers */}
            <Card className="border-border/60 lg:col-span-2">
              <CardHeader className="flex flex-row items-center justify-between pb-2 pt-4">
                <CardTitle className="text-sm font-semibold">最近入库</CardTitle>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1 text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => navigate("/papers")}
                >
                  查看全部
                  <ArrowRight className="h-3 w-3" />
                </Button>
              </CardHeader>
              <CardContent className="pb-3 pt-0">
                {loading ? (
                  <div className="space-y-3">
                    {Array.from({ length: 4 }).map((_, i) => (
                      <div key={i} className="space-y-2">
                        <Skeleton className="h-4 w-3/4" />
                        <Skeleton className="h-3 w-1/3" />
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="divide-y divide-border/60">
                    {recent.map((paper) => (
                      <button
                        key={paper.id}
                        onClick={() => navigate(`/papers/${paper.id}`)}
                        className="flex w-full items-start justify-between gap-3 py-3 text-left transition-colors hover:bg-muted/40"
                      >
                        <div className="min-w-0 flex-1">
                          <h3 className="line-clamp-1 text-sm font-medium text-foreground">
                            {paper.title}
                          </h3>
                          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                            <span className="rounded bg-muted px-1.5 py-0.5 font-medium">
                              {paper.source === "arxiv" ? "arXiv" : "本地"}
                            </span>
                            <span>{paper.published_date}</span>
                            {paper.authors && paper.authors.length > 0 && (
                              <>
                                <span>·</span>
                                <span className="max-w-[120px] truncate">
                                  {paper.authors.slice(0, 2).join(", ")}
                                  {paper.authors.length > 2 && " et al."}
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                        {paper.core_contribution ? (
                          <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400">
                            <Sparkles className="h-3 w-3" />
                            已标注
                          </span>
                        ) : (
                          <span className="inline-flex shrink-0 items-center rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                            未标注
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Quick Actions */}
          <div className="grid gap-3 sm:grid-cols-3">
            {[
              {
                icon: Library,
                label: "管理论文",
                desc: "入库、标注、搜索",
                path: "/papers",
                accent: true,
              },
              {
                icon: Network,
                label: "查看图谱",
                desc: "团队与论文关系",
                path: "/graph",
                accent: false,
              },
              {
                icon: Sparkles,
                label: "智能聊天",
                desc: "向 AI 提问论文内容",
                path: "/chat",
                accent: false,
              },
            ].map((item) => (
              <Card
                key={item.label}
                className="group cursor-pointer border-border/60 transition-all duration-200 hover:shadow-sm"
                onClick={() => navigate(item.path)}
              >
                <CardContent className="flex items-center gap-3 p-4">
                  <div
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors ${
                      item.accent
                        ? "bg-indigo-50 text-indigo-600 group-hover:bg-indigo-100 dark:bg-indigo-950/40 dark:text-indigo-400 dark:group-hover:bg-indigo-950/60"
                        : "bg-muted text-muted-foreground group-hover:bg-muted/80"
                    }`}
                  >
                    <item.icon className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{item.label}</p>
                    <p className="text-[11px] text-muted-foreground">{item.desc}</p>
                  </div>
                  <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground opacity-0 transition-all group-hover:translate-x-1 group-hover:opacity-100" />
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
