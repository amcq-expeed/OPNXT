import type { FormEvent, ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChatModelOption } from "../../lib/api";

export type ChatComposerResourceMenuItem = {
  id: string;
  label: ReactNode;
  icon?: ReactNode;
  accessoryLabel?: ReactNode;
  disabled?: boolean;
  onSelect?: () => void;
};

export type ChatComposerConnectorToggle = {
  id: string;
  label: ReactNode;
  icon?: ReactNode;
  value: boolean;
  disabled?: boolean;
  onChange: (next: boolean) => void;
};

export interface ChatComposerProps {
  draft: string;
  onDraftChange: (value: string) => void;
  onSubmit: (event?: FormEvent<HTMLFormElement>) => void;
  sending?: boolean;
  sendDisabled?: boolean;
  placeholder?: string;
  textareaRows?: number;
  textareaDisabled?: boolean;
  hasSession?: boolean;
  className?: string;
  textareaId?: string;
  textareaRef?: React.RefObject<HTMLTextAreaElement>;
  onDraftInput?: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onTextareaKeyDown?: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onTextareaFocus?: (event: React.FocusEvent<HTMLTextAreaElement>) => void;
  autoFocus?: boolean;

  modelOptions: ChatModelOption[];
  modelLoading?: boolean;
  modelError?: string | null;
  selectedModelKey: string;
  onModelChange: (value: string) => void;

  resourceMenu?: {
    headerLabel?: ReactNode;
    accountLabel?: ReactNode;
    searchPlaceholder?: string;
    items: ChatComposerResourceMenuItem[];
  };
  connectorsMenu?: {
    headerLabel?: ReactNode;
    addConnectorsLabel?: ReactNode;
    items?: ChatComposerResourceMenuItem[];
    toggles?: ChatComposerConnectorToggle[];
    searchPlaceholder?: string;
  };
  extendedThinking?: {
    value: boolean;
    onToggle: (next: boolean) => void;
    icon?: ReactNode;
    tooltip?: string;
    disabled?: boolean;
  };
  sendIcon?: ReactNode;
  modelAriaLabel?: string;
}

export default function ChatComposer({
  draft,
  onDraftChange,
  onSubmit,
  sending = false,
  sendDisabled,
  placeholder = "How can I help you today?",
  textareaRows = 2,
  textareaDisabled = false,
  hasSession = true,
  className,
  textareaId,
  textareaRef,
  onDraftInput,
  onTextareaKeyDown,
  onTextareaFocus,
  autoFocus,
  modelOptions,
  modelLoading = false,
  modelError,
  selectedModelKey,
  onModelChange,
  resourceMenu,
  connectorsMenu,
  extendedThinking,
  sendIcon,
  modelAriaLabel = "Select chat model",
}: ChatComposerProps) {
  const actionsDisabled = !hasSession;
  const [resourceMenuOpen, setResourceMenuOpen] = useState(false);
  const [connectorMenuOpen, setConnectorMenuOpen] = useState(false);
  const resourceMenuRef = useRef<HTMLDivElement | null>(null);
  const resourceMenuButtonRef = useRef<HTMLButtonElement | null>(null);
  const resourceMenuSearchRef = useRef<HTMLInputElement | null>(null);
  const connectorMenuRef = useRef<HTMLDivElement | null>(null);
  const connectorMenuButtonRef = useRef<HTMLButtonElement | null>(null);
  const connectorMenuSearchRef = useRef<HTMLInputElement | null>(null);

  const selectedModelOption = useMemo(() => {
    return modelOptions.find((opt) => `${opt.provider}:${opt.model}` === selectedModelKey) ?? null;
  }, [modelOptions, selectedModelKey]);

  useEffect(() => {
    if (!resourceMenuOpen) return;
    const clickHandler = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        resourceMenuRef.current?.contains(target) ||
        resourceMenuButtonRef.current?.contains(target)
      ) {
        return;
      }
      setResourceMenuOpen(false);
    };
    const keyHandler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setResourceMenuOpen(false);
        resourceMenuButtonRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", clickHandler);
    document.addEventListener("keydown", keyHandler);
    const timer = window.setTimeout(() => resourceMenuSearchRef.current?.focus(), 20);
    return () => {
      document.removeEventListener("mousedown", clickHandler);
      document.removeEventListener("keydown", keyHandler);
      window.clearTimeout(timer);
    };
  }, [resourceMenuOpen]);

  useEffect(() => {
    if (!connectorMenuOpen) return;
    const clickHandler = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        connectorMenuRef.current?.contains(target) ||
        connectorMenuButtonRef.current?.contains(target)
      ) {
        return;
      }
      setConnectorMenuOpen(false);
    };
    const keyHandler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setConnectorMenuOpen(false);
        connectorMenuButtonRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", clickHandler);
    document.addEventListener("keydown", keyHandler);
    const timer = window.setTimeout(() => connectorMenuSearchRef.current?.focus(), 20);
    return () => {
      document.removeEventListener("mousedown", clickHandler);
      document.removeEventListener("keydown", keyHandler);
      window.clearTimeout(timer);
    };
  }, [connectorMenuOpen]);

  const handleSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      onSubmit(event);
    },
    [onSubmit],
  );

  const wrapperClass = className ? `chat-composer ${className}` : "chat-composer";

  return (
    <div className={wrapperClass}>
      <form onSubmit={handleSubmit} className="chat-composer__form">
        <div className="composer-shell">
          <div className="composer-shell__input">
            <textarea
              id={textareaId}
              ref={textareaRef}
              value={draft}
              onChange={(event) => {
                onDraftChange(event.target.value);
                onDraftInput?.(event);
              }}
              placeholder={placeholder}
              rows={textareaRows}
              disabled={textareaDisabled}
              autoFocus={autoFocus}
              onKeyDown={onTextareaKeyDown}
              onFocus={onTextareaFocus}
            />
          </div>
          <div className="composer-shell__footer">
            <div className="composer-pills" role="group" aria-label="Composer actions">
              {resourceMenu ? (
                <>
                  <button
                    type="button"
                    className={resourceMenuOpen ? "composer-pill composer-pill--active" : "composer-pill"}
                    onClick={() => {
                      if (actionsDisabled) return;
                      setConnectorMenuOpen(false);
                      setResourceMenuOpen((open) => !open);
                    }}
                    disabled={actionsDisabled}
                    aria-haspopup="true"
                    aria-expanded={resourceMenuOpen}
                    aria-controls="chat-composer-resource-menu"
                    aria-label={resourceMenuOpen ? "Close resources menu" : "Open resources menu"}
                    title={resourceMenuOpen ? "Close menu" : "Add resources"}
                    ref={resourceMenuButtonRef}
                  >
                    <span aria-hidden="true">{resourceMenuOpen ? "✕" : "＋"}</span>
                  </button>
                  <div
                    id="chat-composer-resource-menu"
                    className={resourceMenuOpen ? "composer-menu composer-menu--open" : "composer-menu"}
                    role="menu"
                    ref={resourceMenuRef}
                  >
                    <div className="composer-menu__header">
                      <span>{resourceMenu.headerLabel ?? "Use a project"}</span>
                      {resourceMenu.accountLabel ? (
                        <span className="composer-menu__account">{resourceMenu.accountLabel}</span>
                      ) : null}
                    </div>
                    <ul className="composer-menu__list">
                      {resourceMenu.items.map((item) => (
                        <li role="none" key={item.id}>
                          <button
                            type="button"
                            role="menuitem"
                            disabled={item.disabled}
                            onClick={() => {
                              if (item.disabled) return;
                              item.onSelect?.();
                              setResourceMenuOpen(false);
                            }}
                          >
                            {item.icon ? <span className="composer-menu__icon" aria-hidden="true">{item.icon}</span> : null}
                            <span>{item.label}</span>
                            {item.accessoryLabel ? (
                              <span className="composer-menu__link" aria-hidden="true">
                                {item.accessoryLabel}
                              </span>
                            ) : null}
                          </button>
                        </li>
                      ))}
                    </ul>
                    {resourceMenu.searchPlaceholder ? (
                      <div className="composer-menu__search">
                        <span aria-hidden="true">🔍</span>
                        <input
                          type="text"
                          placeholder={resourceMenu.searchPlaceholder}
                          ref={resourceMenuSearchRef}
                          aria-label={resourceMenu.searchPlaceholder}
                        />
                      </div>
                    ) : null}
                  </div>
                </>
              ) : null}
              {connectorsMenu ? (
                <>
                  <button
                    type="button"
                    className={connectorMenuOpen ? "composer-pill composer-pill--active" : "composer-pill"}
                    onClick={() => {
                      if (actionsDisabled) return;
                      setResourceMenuOpen(false);
                      setConnectorMenuOpen((open) => !open);
                    }}
                    disabled={actionsDisabled}
                    aria-haspopup="true"
                    aria-expanded={connectorMenuOpen}
                    aria-controls="chat-composer-connector-menu"
                    aria-label={connectorMenuOpen ? "Close connector menu" : "Manage connectors"}
                    title={connectorMenuOpen ? "Close connector menu" : "Manage connectors"}
                    ref={connectorMenuButtonRef}
                  >
                    <span aria-hidden="true">⚙</span>
                  </button>
                  <div
                    id="chat-composer-connector-menu"
                    className={connectorMenuOpen ? "composer-menu composer-menu--open" : "composer-menu"}
                    role="menu"
                    ref={connectorMenuRef}
                  >
                    <div className="composer-menu__header">
                      <span>{connectorsMenu.headerLabel ?? "Manage connectors"}</span>
                      {connectorsMenu.addConnectorsLabel ? (
                        <button type="button" className="composer-menu__link" disabled>
                          {connectorsMenu.addConnectorsLabel}
                        </button>
                      ) : null}
                    </div>
                    {connectorsMenu.items?.length ? (
                      <ul className="composer-menu__list">
                        {connectorsMenu.items.map((item) => (
                          <li role="none" key={item.id}>
                            <button type="button" role="menuitem" disabled={item.disabled} onClick={item.onSelect}>
                              {item.icon ? (
                                <span className="composer-menu__icon" aria-hidden="true">
                                  {item.icon}
                                </span>
                              ) : null}
                              <span>{item.label}</span>
                              {item.accessoryLabel ? (
                                <span className="composer-menu__link" aria-hidden="true">
                                  {item.accessoryLabel}
                                </span>
                              ) : null}
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    {connectorsMenu.toggles?.length ? (
                      <>
                        <hr className="composer-menu__divider" />
                        <ul className="composer-menu__list">
                          {connectorsMenu.toggles.map((toggle) => (
                            <li role="none" key={toggle.id}>
                              <label className="composer-menu__toggle" role="menuitem">
                                {toggle.icon ? (
                                  <span className="composer-menu__icon" aria-hidden="true">
                                    {toggle.icon}
                                  </span>
                                ) : null}
                                <span>{toggle.label}</span>
                                <input
                                  type="checkbox"
                                  checked={toggle.value}
                                  onChange={(event) => toggle.onChange(event.target.checked)}
                                  disabled={toggle.disabled}
                                  aria-label={typeof toggle.label === "string" ? toggle.label : undefined}
                                />
                                <span className="composer-menu__switch" aria-hidden="true" />
                              </label>
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : null}
                    {connectorsMenu.searchPlaceholder ? (
                      <div className="composer-menu__search">
                        <span aria-hidden="true">🔍</span>
                        <input
                          type="text"
                          placeholder={connectorsMenu.searchPlaceholder}
                          ref={connectorMenuSearchRef}
                          aria-label={connectorsMenu.searchPlaceholder}
                        />
                      </div>
                    ) : null}
                  </div>
                </>
              ) : null}
              {extendedThinking ? (
                <button
                  type="button"
                  className={extendedThinking.value ? "composer-pill composer-pill--active" : "composer-pill"}
                  onClick={() => {
                    if (actionsDisabled || extendedThinking.disabled) return;
                    setResourceMenuOpen(false);
                    setConnectorMenuOpen(false);
                    extendedThinking.onToggle(!extendedThinking.value);
                  }}
                  disabled={actionsDisabled || extendedThinking.disabled}
                  aria-pressed={extendedThinking.value}
                  aria-label={extendedThinking.tooltip ?? "Toggle extended thinking"}
                  title={extendedThinking.tooltip ?? "Extended thinking"}
                >
                  <span aria-hidden="true">{extendedThinking.icon ?? "🧠"}</span>
                </button>
              ) : null}
            </div>
            <div className="composer-shell__footerRight">
              <div className="composer-model">
                <select
                  value={selectedModelOption ? `${selectedModelOption.provider}:${selectedModelOption.model}` : selectedModelKey}
                  onChange={(event) => onModelChange(event.target.value)}
                  disabled={modelLoading || modelOptions.length === 0}
                  aria-label={modelAriaLabel}
                >
                  {modelOptions.map((option) => (
                    <option
                      key={`${option.provider}:${option.model}`}
                      value={`${option.provider}:${option.model}`}
                      disabled={!option.available && !option.adaptive}
                    >
                      {option.label}
                      {!option.available ? " (Unavailable)" : ""}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="submit"
                className="composer-send"
                disabled={(sendDisabled ?? sending) || !draft.trim() || !hasSession}
                aria-busy={sending || undefined}
              >
                {sending ? "…" : sendIcon ?? <span aria-hidden="true">↑</span>}
                <span className="sr-only">Send message</span>
              </button>
            </div>
          </div>
        </div>
        {modelError ? <div className="composer-model__error" role="alert">{modelError}</div> : null}
      </form>
    </div>
  );
}
