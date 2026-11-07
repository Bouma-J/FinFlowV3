import { Download, MoreVertical } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "@/api/client";

export function CreditDossierMenu({
  applicationId,
  reference,
}: {
  applicationId: string;
  reference: string;
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [place, setPlace] = useState({ top: 0, right: 0 });
  const root = useRef<HTMLDivElement>(null);

  function toggle() {
    if (!open && root.current) {
      const rect = root.current.getBoundingClientRect();
      setPlace({
        top: rect.bottom + 6,
        right: Math.max(8, window.innerWidth - rect.right),
      });
    }
    setOpen((value) => !value);
  }

  useEffect(() => {
    if (!open) return;
    function onPointer(event: MouseEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function exportPdf() {
    setPending(true);
    setError(null);
    try {
      const response = await api.get(
        `/credit-applications/${applicationId}/export-pdf/`,
        { responseType: "blob" },
      );
      const blob = response.data as Blob;
      if (blob.type.includes("json") || blob.type.includes("text")) {
        throw new Error("L'export PDF a échoué.");
      }
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const safe = (reference || applicationId.slice(0, 8)).replace(/[^\w.-]+/g, "-");
      link.href = url;
      link.download = `dossier-${safe}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
      setOpen(false);
    } catch {
      setError("L'export PDF a échoué.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="dossier-menu" ref={root}>
      <button
        type="button"
        className="dossier-menu-btn"
        aria-label="Actions du dossier"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={toggle}
      >
        <MoreVertical size={16} />
      </button>
      {open && (
        <div
          className="dossier-menu-panel"
          role="menu"
          style={{ top: place.top, right: place.right }}
        >
          <button
            type="button"
            className="dossier-menu-item"
            role="menuitem"
            disabled={pending}
            onClick={exportPdf}
          >
            <Download size={14} />
            {pending ? "Préparation du PDF…" : "Exporter le dossier en PDF"}
          </button>
          {error && <p className="dossier-menu-error">{error}</p>}
        </div>
      )}
    </div>
  );
}
