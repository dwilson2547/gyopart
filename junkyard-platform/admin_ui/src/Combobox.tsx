import { useEffect, useId, useMemo, useRef, useState } from "react";

export type Option = { value: string; label: string; hint?: string; dim?: boolean };

/** Searchable single-select over a live list. Typing filters; ↑/↓ + Enter or click picks; Esc closes.
 *  Only listed values can be chosen, so nothing typed ever reaches the server as a value. */
export function Combobox({ options, value, onChange, placeholder, label, autoFocus, invalid }: {
  options: Option[]; value: string | null; onChange: (v: string | null) => void; placeholder?: string;
  label: string; autoFocus?: boolean; invalid?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const box = useRef<HTMLDivElement>(null);
  const current = options.find((o) => o.value === value) ?? null;

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    const hits = q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options;
    return hits.slice(0, 200);
  }, [options, query]);

  useEffect(() => { setActive(0); }, [query, open]);
  useEffect(() => {
    const away = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, []);

  const pick = (o: Option) => { onChange(o.value); setQuery(""); setOpen(false); };

  return (
    <div className={`combo${invalid ? " invalid" : ""}`} ref={box}>
      <input
        role="combobox" aria-label={label} aria-expanded={open} aria-controls={listId} autoFocus={autoFocus}
        placeholder={current ? current.label : placeholder} value={open ? query : current?.label ?? ""}
        onFocus={() => setOpen(true)}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, shown.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
          else if (e.key === "Enter" && open && shown[active]) { e.preventDefault(); pick(shown[active]); }
          else if (e.key === "Escape") { setOpen(false); setQuery(""); }
        }}
      />
      {value && !open && (
        <button type="button" className="combo-clear" aria-label={`clear ${label}`} onClick={() => onChange(null)}>×</button>
      )}
      {open && (
        <ul className="combo-list" id={listId} role="listbox">
          {shown.length === 0 && <li className="muted combo-none">no match</li>}
          {shown.map((o, i) => (
            <li key={o.value} role="option" aria-selected={o.value === value}
                className={`${i === active ? "active" : ""}${o.dim ? " dim" : ""}`}
                onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); pick(o); }}>
              <span>{o.label}</span>{o.hint && <span className="muted combo-hint">{o.hint}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
