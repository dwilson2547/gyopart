---
title: Phase 6 — gyopart-ui React Patterns & Gotchas
date: 2026-05-31
tags: gyopart-ui, react, typescript, tailwind, phase-6
---

gyopart-ui lives at gyopart/gyopart-ui/. Vite + React 18 + TypeScript + Tailwind CSS v4 (@tailwindcss/vite plugin). index.css contains only @import "tailwindcss". Env var: VITE_API_BASE_URL (default http://localhost:8200). Cascading vehicle picker gotcha: use controlled selects (value prop) not uncontrolled (defaultValue) — uncontrolled selects do not reset when parent selection changes. Add key={parent.sel.id} on each downstream select to force remount when parent changes. PartsList useEffect gotcha: always add a cancelled flag + cleanup return to prevent stale data race and stuck loading state on rejection — also add .catch() handler or loading stays true forever. useVehicleTree closure gotcha: use setSel({ ...sel, ... }) direct spread instead of setSel(s => ...) functional updater when also reading sel in the same function, to avoid stale closure reads. ZipInput unmount guard: use mounted ref + useEffect cleanup to prevent dispatches on unmounted component during in-flight search. JunkyardResults: add key={state.activePart.id} to ZipInput so local zip/radius state resets when part changes. AppContext uses useReducer; Dispatch<Action> must be imported from react — React.Dispatch is unavailable without namespace import.
