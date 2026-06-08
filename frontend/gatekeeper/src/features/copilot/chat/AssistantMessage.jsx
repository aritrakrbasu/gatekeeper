import React, { useEffect, useRef, useState } from "react";
import { TerminalMarkdown } from "../../../components/shared";

const CHARS_PER_FRAME = 4;

export function AssistantMessage({ content, streaming = false }) {
  const [visibleContent, setVisibleContent] = useState("");
  const targetRef = useRef("");
  const indexRef = useRef(0);
  const frameRef = useRef(null);

  useEffect(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }

    if (!streaming) {
      indexRef.current = 0;
      setVisibleContent(content || "");
      return undefined;
    }

    const target = content || "";
    targetRef.current = target;

    if (!target) {
      indexRef.current = 0;
      setVisibleContent("");
      return undefined;
    }

    let cancelled = false;

    setVisibleContent((previous) => {
      if (target.startsWith(previous)) {
        indexRef.current = previous.length;
      } else {
        indexRef.current = 0;
      }
      return previous;
    });

    const step = () => {
      if (cancelled) {
        return;
      }

      const nextTarget = targetRef.current;
      if (indexRef.current >= nextTarget.length) {
        setVisibleContent(nextTarget);
        return;
      }

      indexRef.current = Math.min(
        indexRef.current + CHARS_PER_FRAME,
        nextTarget.length,
      );
      setVisibleContent(nextTarget.slice(0, indexRef.current));

      if (indexRef.current < nextTarget.length) {
        frameRef.current = requestAnimationFrame(step);
      }
    };

    frameRef.current = requestAnimationFrame(step);

    return () => {
      cancelled = true;
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
    };
  }, [content, streaming]);

  const showThinking = streaming && !visibleContent;

  return (
    <div className="flex justify-start">
      <div className="max-w-[95%] w-full bg-slate-900 rounded-2xl px-4 py-3 shadow-sm">
        {showThinking ? (
          <p className="text-slate-500 text-sm italic">Thinking...</p>
        ) : visibleContent ? (
          <div>
            <TerminalMarkdown>{visibleContent}</TerminalMarkdown>
            {streaming ? (
              <span className="inline-block w-2 h-4 ml-1 bg-[#FC6D26] animate-pulse align-middle" />
            ) : null}
          </div>
        ) : (
          <p className="text-slate-500 text-sm italic">No response yet.</p>
        )}
      </div>
    </div>
  );
}
