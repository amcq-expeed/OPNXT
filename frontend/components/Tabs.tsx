import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

export interface TabItem {
  id: string;
  label: string;
  content: ReactNode;
}

interface TabsProps {
  tabs: TabItem[];
  defaultTabId?: string;
}

export default function Tabs({ tabs, defaultTabId }: TabsProps) {
  const [activeId, setActiveId] = useState<string>(
    defaultTabId || (tabs[0]?.id ?? ""),
  );
  const listRef = useRef<HTMLDivElement | null>(null);
  const tabIds = useMemo(() => tabs.map((t) => t.id), [tabs]);
  const baseId = useId();

  useEffect(() => {
    if (!tabIds.includes(activeId) && tabIds.length) setActiveId(tabIds[0]);
  }, [activeId, tabIds]);

  function onKeyDown(e: React.KeyboardEvent) {
    if (
      e.key !== "ArrowRight" &&
      e.key !== "ArrowLeft" &&
      e.key !== "Home" &&
      e.key !== "End"
    )
      return;
    e.preventDefault();
    const idx = tabIds.indexOf(activeId);
    if (idx < 0) return;
    let nextIdx = idx;
    if (e.key === "ArrowRight") nextIdx = (idx + 1) % tabIds.length;
    else if (e.key === "ArrowLeft")
      nextIdx = (idx - 1 + tabIds.length) % tabIds.length;
    else if (e.key === "Home") nextIdx = 0;
    else if (e.key === "End") nextIdx = tabIds.length - 1;
    const nextId = tabIds[nextIdx];
    setActiveId(nextId);
    const btnId = `${baseId}-tab-${nextId}`;
    const btn = document.getElementById(btnId) as HTMLButtonElement | null;
    if (btn) btn.focus();
  }

  return (
    <div className="tabs">
      <div
        className="tablist"
        role="tablist"
        aria-label="Project workspace tabs"
        onKeyDown={onKeyDown}
        ref={listRef}
      >
        {tabs.map((t) => (
          <button
            key={t.id}
            className="tab"
            role="tab"
            data-tab-id={t.id}
            aria-selected={activeId === t.id}
            aria-controls={`${baseId}-panel-${t.id}`}
            id={`${baseId}-tab-${t.id}`}
            onClick={() => setActiveId(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tabs.map((t) => (
        <div
          key={t.id}
          id={`${baseId}-panel-${t.id}`}
          role="tabpanel"
          aria-labelledby={`${baseId}-tab-${t.id}`}
          hidden={activeId !== t.id}
          className="tabpanel"
        >
          {t.content}
        </div>
      ))}
    </div>
  );
}
