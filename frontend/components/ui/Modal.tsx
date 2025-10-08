import { ReactNode, useEffect, useMemo } from "react";
import { createPortal } from "react-dom";

export type ModalProps = {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  footer?: ReactNode;
  size?: "md" | "lg" | "xl";
};

const sizeToWidth: Record<NonNullable<ModalProps["size"]>, string> = {
  md: "min(640px, 92vw)",
  lg: "min(840px, 94vw)",
  xl: "min(1040px, 96vw)",
};

export default function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  size = "lg",
}: ModalProps) {
  const target = useMemo(() => {
    if (typeof window === "undefined") return null;
    return document.body;
  }, []);

  useEffect(() => {
    if (!open || typeof document === "undefined") return undefined;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", handleKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKey);
    };
  }, [open, onClose]);

  if (!open || !target) return null;

  const width = sizeToWidth[size] || sizeToWidth.lg;

  return createPortal(
    <div
      className="modal-backdrop"
      role="presentation"
      onClick={onClose}
      aria-hidden="true"
    >
      <div
        className="modal-shell"
        role="dialog"
        aria-modal="true"
        aria-label={title || "Dialog"}
        style={{ width }}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-header">
          <h3>{title}</h3>
          <button className="btn" type="button" onClick={onClose}>
            Close
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-footer">{footer}</footer>}
      </div>
    </div>,
    target,
  );
}
