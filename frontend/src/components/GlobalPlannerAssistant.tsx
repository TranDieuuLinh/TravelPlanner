"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { PenguinMascot } from "@/components/PenguinMascot";
import {
  PlannerChatComposer,
  PlannerChatHeader,
  PlannerChatMessages,
} from "@/components/PlannerChatUI";

export function GlobalPlannerAssistant() {
  const pathname = usePathname();
  const router = useRouter();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [urlInput, setUrlInput] = useState("");
  const [reelViewerOpen, setReelViewerOpen] = useState(false);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(
    null
  );
  const dragRef = useRef<{
    left: number;
    pointerId: number;
    startX: number;
    startY: number;
    top: number;
  } | null>(null);

  useEffect(() => {
    const handleReelViewerChange = (event: Event) => {
      const viewerOpen = event instanceof CustomEvent && Boolean(event.detail?.open);
      setReelViewerOpen(viewerOpen);
      if (viewerOpen) setOpen(false);
    };

    window.addEventListener("vsf:reel-viewer-change", handleReelViewerChange);
    return () => window.removeEventListener("vsf:reel-viewer-change", handleReelViewerChange);
  }, []);

  useEffect(() => {
    if (!open) return;

    inputRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  if (pathname.startsWith("/planner") || reelViewerOpen) return null;

  function openPlanner(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = [prompt.trim(), urlInput.trim()].filter(Boolean).join("\n");
    router.push(message ? `/planner?prompt=${encodeURIComponent(message)}` : "/planner");
    setOpen(false);
  }

  function beginMove(event: ReactPointerEvent<HTMLButtonElement>) {
    const panel = event.currentTarget.closest<HTMLElement>(
      ".explorePlannerChat"
    );
    if (!panel) return;
    const rect = panel.getBoundingClientRect();
    dragRef.current = {
      left: rect.left,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      top: rect.top,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setPosition({ left: rect.left, top: rect.top });
  }

  function updateMove(event: ReactPointerEvent<HTMLButtonElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const panel = event.currentTarget.closest<HTMLElement>(
      ".explorePlannerChat"
    );
    const width = panel?.offsetWidth ?? 410;
    const height = panel?.offsetHeight ?? 610;
    setPosition({
      left: Math.min(
        Math.max(8, drag.left + event.clientX - drag.startX),
        Math.max(8, window.innerWidth - width - 8)
      ),
      top: Math.min(
        Math.max(8, drag.top + event.clientY - drag.startY),
        Math.max(8, window.innerHeight - height - 8)
      ),
    });
  }

  function endMove(event: ReactPointerEvent<HTMLButtonElement>) {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  return (
    <aside
      aria-label="Trợ lý lập kế hoạch VSF"
      className={`globalPlannerAssistant ${open ? "is-open" : ""}`}
      style={
        position
          ? ({
              bottom: "auto",
              left: `${position.left}px`,
              right: "auto",
              top: `${position.top}px`,
            } as CSSProperties)
          : undefined
      }
    >
      {open ? (
        <section
          aria-labelledby="global-planner-title"
          className="explorePlannerChat plannerChat plannerChat--compact panel"
        >
          <PlannerChatHeader
            contentId="global-planner-chat-content"
            moveHandleProps={{
              onPointerCancel: endMove,
              onPointerDown: beginMove,
              onPointerMove: updateMove,
              onPointerUp: endMove,
            }}
            onToggle={() => setOpen(false)}
            status="Cùng bạn xây dựng chuyến đi"
            titleId="global-planner-title"
          />
          <div
            className="plannerChatContent"
            id="global-planner-chat-content"
          >
            <PlannerChatMessages
              messages={[
                {
                  id: "global-planner-welcome",
                  role: "assistant",
                  text: "Bạn muốn đi đâu? Hãy mô tả chuyến đi hoặc dán URL video; mình sẽ mở AI Planner để tiếp tục.",
                },
              ]}
            />
            <PlannerChatComposer
              onPromptChange={setPrompt}
              onSubmit={openPlanner}
              onUrlChange={setUrlInput}
              prompt={prompt}
              promptPlaceholder="Mô tả chuyến đi bạn mong muốn…"
              promptRef={inputRef}
              urlInput={urlInput}
            />
          </div>
          <div
            aria-hidden="true"
            className="plannerChatResizeHandles explorePlannerResizeHint"
          >
            <span className="plannerChatResizeHandle plannerChatResizeHandle--se">
              <svg aria-hidden="true" viewBox="0 0 18 18">
                <path d="M7 15h8V7M11 15h4v-4" />
              </svg>
            </span>
          </div>
        </section>
      ) : (
        <button
          aria-expanded="false"
          aria-label="Mở trợ lý lập kế hoạch VSF"
          className="globalPlannerLauncher"
          onClick={() => setOpen(true)}
          type="button"
        >
          <span className="globalPlannerLauncherArtwork">
            <PenguinMascot className="globalPlannerPenguin" size={82} variant="chatSpeaking" />
            <svg aria-hidden="true" className="globalPlannerBubble" viewBox="0 0 24 24">
              <path d="M5.25 4.75h13.5A2.25 2.25 0 0 1 21 7v8.5a2.25 2.25 0 0 1-2.25 2.25H11l-4.75 3v-3h-1A2.25 2.25 0 0 1 3 15.5V7a2.25 2.25 0 0 1 2.25-2.25Z" />
              <circle cx="8" cy="11.25" r="1" />
              <circle cx="12" cy="11.25" r="1" />
              <circle cx="16" cy="11.25" r="1" />
            </svg>
          </span>
          <span className="globalPlannerLauncherLabel">Hỏi Planner</span>
        </button>
      )}
    </aside>
  );
}
