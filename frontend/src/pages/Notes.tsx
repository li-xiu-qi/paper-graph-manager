import { useState, useEffect } from "react";
import { FileTree } from "@/components/FileTree";
import { NoteEditor } from "@/components/NoteEditor";
import { Button } from "@/components/ui/button";
import type { NoteItem } from "@/types";
import { ArrowLeft } from "lucide-react";

export function Notes() {
  const [activeNote, setActiveNote] = useState<NoteItem | undefined>(undefined);
  const [mobileShowEditor, setMobileShowEditor] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768);
    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  const handleSelectNote = (note: NoteItem) => {
    setActiveNote(note);
    if (isMobile) {
      setMobileShowEditor(true);
    }
  };

  const handleBackToList = () => {
    setMobileShowEditor(false);
    setActiveNote(undefined);
  };

  return (
    <div className="flex h-[calc(100vh-7rem)] min-h-[60vh] flex-col">
      <div className="mb-3">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">笔记管理</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">浏览、编辑和管理你的 Markdown 笔记</p>
      </div>

      <div className="relative flex flex-1 min-h-0 flex-col gap-3 md:flex-row">
        {/* File Tree */}
        <div
          className={cn(
            "h-full w-full overflow-hidden rounded-xl border border-border/60 bg-card md:w-80 md:shrink-0",
            isMobile && mobileShowEditor ? "hidden" : "block"
          )}
        >
          <FileTree activeNoteId={activeNote?.paper_id} onSelectNote={handleSelectNote} />
        </div>

        {/* Editor */}
        <div
          className={cn(
            "flex h-full flex-1 min-h-0 flex-col overflow-hidden rounded-xl border border-border/60 bg-card p-4",
            isMobile && !mobileShowEditor ? "hidden" : "block"
          )}
        >
          {isMobile && mobileShowEditor && (
            <div className="mb-3 md:hidden">
              <Button variant="outline" size="sm" className="gap-1" onClick={handleBackToList}>
                <ArrowLeft className="h-4 w-4" />
                返回笔记列表
              </Button>
            </div>
          )}
          <NoteEditor
            noteId={activeNote?.paper_id}
            noteTitle={activeNote?.title}
            onSelectAnother={() => {
              setActiveNote(undefined);
              setMobileShowEditor(false);
            }}
          />
        </div>
      </div>
    </div>
  );
}

function cn(...classes: (string | false | undefined | null)[]) {
  return classes.filter(Boolean).join(" ");
}
