import { useState, useEffect, lazy, Suspense } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { fetchGraphTeam, fetchGraphPaper } from "@/services/api";
import type { GraphData } from "@/types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Search, RotateCcw, Loader2, X, Network, Library } from "lucide-react";

const PixiGraph = lazy(() =>
  import("@/components/PixiGraph").then((module) => ({ default: module.PixiGraph })),
);

const NODE_COLORS = {
  team: "#4f46e5", // indigo-600
  paper: "#64748b", // slate-500
  default: "#94a3b8", // slate-400
};

function Legend() {
  return (
    <div className="absolute bottom-4 left-4 z-10 rounded-xl border border-border/60 bg-card/95 p-3 shadow-sm backdrop-blur-sm">
      <p className="mb-2 text-xs font-medium text-muted-foreground">图例</p>
      <div className="space-y-1.5">
        <div className="flex items-center gap-2 text-xs">
          <span
            className="h-2.5 w-2.5 rounded-full"
            style={{ backgroundColor: NODE_COLORS.team }}
          />
          <span>团队</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span
            className="h-2.5 w-2.5 rounded-full"
            style={{ backgroundColor: NODE_COLORS.paper }}
          />
          <span>论文</span>
        </div>
      </div>
    </div>
  );
}

export function Graph() {
  const navigate = useNavigate();
  const [teamData, setTeamData] = useState<GraphData | null>(null);
  const [paperData, setPaperData] = useState<GraphData | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedNode, setSelectedNode] = useState<any>(null);

  useEffect(() => {
    Promise.all([fetchGraphTeam(), fetchGraphPaper()]).then(([team, paper]) => {
      setTeamData(team);
      setPaperData(paper);
    });
  }, []);

  const handleReset = () => {
    setSearchQuery("");
    setSelectedNode(null);
  };

  const getNodeColor = (node: any) => {
    if (node.group === "team") return NODE_COLORS.team;
    if (node.group === "paper") return NODE_COLORS.paper;
    return NODE_COLORS.default;
  };

  const renderGraph = (data: GraphData | null, view: string) => {
    if (!data || !data.nodes || data.nodes.length === 0) {
      return (
        <Card className="border-border/60">
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted">
              {view === "team" ? (
                <Network className="h-7 w-7 text-muted-foreground" />
              ) : (
                <Library className="h-7 w-7 text-muted-foreground" />
              )}
            </div>
            <h3 className="mt-4 text-base font-semibold">
              {view === "team" ? "暂无团队数据" : "暂无论文数据"}
            </h3>
            <p className="mt-1 max-w-sm text-xs text-muted-foreground">
              {view === "team"
                ? "请先对论文执行智能标注以生成团队信息。"
                : "请先入库一些论文。"}
            </p>
            <Button
              onClick={() => navigate("/papers")}
              variant="secondary"
              size="sm"
              className="mt-5"
            >
              前往论文管理
            </Button>
          </CardContent>
        </Card>
      );
    }

    const safeData = {
      nodes: (data.nodes || []).map((node) => ({
        ...node,
        id: node.id || "",
        label: node.label || node.id || "",
        title: node.title || "",
        group: node.group || "default",
      })),
      edges: (data.edges || []).map((edge) => ({
        ...edge,
        source: (edge as any).source || "",
        target: (edge as any).target || "",
      })),
    };

    const filteredData = searchQuery
      ? {
          ...safeData,
          nodes: safeData.nodes.filter(
            (node) =>
              node.label?.toLowerCase().includes(searchQuery.toLowerCase()) ||
              node.title?.toLowerCase().includes(searchQuery.toLowerCase())
          ),
          edges: safeData.edges.filter((edge) => {
            const nodeIds = new Set(safeData.nodes.map((n) => n.id));
            return nodeIds.has(edge.source) && nodeIds.has(edge.target);
          }),
        }
      : safeData;

    return (
      <Card className="flex h-[calc(100vh-12rem)] min-h-[320px] flex-col border-border/60 sm:h-[calc(100vh-11rem)]">
        <CardContent className="relative flex flex-1 flex-col p-0">
          <div className="flex items-center gap-2 border-b border-border/60 p-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="搜索节点..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
                aria-label="搜索图谱节点"
              />
            </div>
            <Button variant="outline" size="icon" onClick={handleReset} title="重置" aria-label="重置搜索">
              <RotateCcw className="h-4 w-4" />
            </Button>
          </div>

          <div className="relative flex-1 min-h-0 overflow-hidden rounded-b-xl">
            <Suspense
              fallback={(
                <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  正在加载图引擎...
                </div>
              )}
            >
              <PixiGraph
                data={filteredData}
                nodeColor={getNodeColor}
                onNodeClick={(node) => setSelectedNode(node)}
                className="h-full w-full rounded-b-xl"
              />
            </Suspense>

            <Legend />

            {selectedNode && (
              <div className="absolute right-3 top-3 z-10 w-72 max-w-[calc(100vw-1.5rem)]">
                <Card className="border-border/60 shadow-lg">
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <Badge
                          variant={selectedNode.group === "team" ? "default" : "secondary"}
                          className={
                            selectedNode.group === "team"
                              ? "bg-indigo-600 text-white hover:bg-indigo-700 dark:bg-indigo-600 dark:hover:bg-indigo-500"
                              : ""
                          }
                        >
                          {selectedNode.group === "team" ? "团队" : "论文"}
                        </Badge>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="-mr-2 -mt-2 h-7 w-7"
                        onClick={() => setSelectedNode(null)}
                        aria-label="关闭节点详情"
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                    <h4 className="mt-3 font-medium line-clamp-2">
                      {selectedNode.label || selectedNode.id}
                    </h4>
                    {selectedNode.title && (
                      <p className="mt-1 line-clamp-3 text-sm text-muted-foreground">
                        {selectedNode.title}
                      </p>
                    )}
                    <p className="mt-3 text-xs text-muted-foreground">ID: {selectedNode.id}</p>
                  </CardContent>
                </Card>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    );
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-balance">知识图谱</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">交互式探索论文与团队关系</p>
      </div>

      <Tabs defaultValue="team" className="w-full">
        <TabsList>
          <TabsTrigger value="team">团队视图</TabsTrigger>
          <TabsTrigger value="paper">论文视图</TabsTrigger>
        </TabsList>
        <TabsContent value="team" className="mt-4">
          {renderGraph(teamData, "team")}
        </TabsContent>
        <TabsContent value="paper" className="mt-4">
          {renderGraph(paperData, "paper")}
        </TabsContent>
      </Tabs>
    </div>
  );
}
