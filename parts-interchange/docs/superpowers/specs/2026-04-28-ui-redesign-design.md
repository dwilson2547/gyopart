# UI Redesign — Parts Interchange v2

**Date:** 2026-04-28  
**Status:** Approved  
**Output directory:** `ui-v2/`

---

## Overview

A complete rewrite of the parts interchange UI using React, Tailwind CSS, and shadcn/ui. The goal is a responsive, dark-industrial reference tool that lets a junkyard user quickly identify which other vehicles share a specific OEM part number with their own car.

The existing API remains unchanged. Models are not modified. New API routes may be added if needed but no existing routes will be altered.

---

## Tech Stack

| Concern | Choice |
|---|---|
| Framework | React 18 (Vite) |
| Styling | Tailwind CSS v3 |
| Component library | shadcn/ui (Radix UI primitives) |
| HTTP client | axios |
| State | React context + useReducer (no external state lib) |
| Persistence | Browser localStorage |
| Build output | `ui-v2/` at project root |

---

## Color System

| Token | Value | Usage |
|---|---|---|
| `slate-950` | `#020617` | Page body background |
| `slate-900` | `#0f172a` | Panel backgrounds |
| `slate-800` | `#1e293b` | Dividers, table row alternates, chips |
| `zinc-400` | `#a1a1aa` | Secondary / metadata text |
| `white` | `#ffffff` | Primary text |
| `amber-500` | `#f59e0b` | Accent: active states, highlights, part numbers |

---

## Layout — Desktop

```
┌─────────────────────────────────────────────────────────────┐
│ TOP BAR (fixed, full-width, slate-900, h-14)                │
│  [Logo / App Name]   [Active Vehicle Badge]   [Feedback]    │
├──────────────────────┬──────────────────────────────────────┤
│ LEFT RAIL (320px)    │ RIGHT PANEL (flex-1)                 │
│                      │                                      │
│ ┌──────────────────┐ │ ┌──────────────────────────────────┐ │
│ │  Vehicle Picker  │ │ │  Part Detail Header              │ │
│ │  (collapsible)   │ │ │  Part# · Title · Image · Chips   │ │
│ ├──────────────────┤ │ ├──────────────────────────────────┤ │
│ │  Garage          │ │ │  Interchange Table               │ │
│ │  (saved cars)    │ │ │  Filter · Row count              │ │
│ ├──────────────────┤ │ │  Year Make Model Trim Engine     │ │
│ │  Parts Search    │ │ │  (sortable, amber active row)    │ │
│ │  [search input]  │ │ │                                  │ │
│ │  [part cards...] │ │ │                                  │ │
│ └──────────────────┘ │ └──────────────────────────────────┘ │
└──────────────────────┴──────────────────────────────────────┘
```

The left rail is fixed-width (320px) and full-height with independent scroll. The right panel fills remaining width and height.

---

## Layout — Mobile

A bottom tab bar with two tabs replaces the side-by-side layout:

- **Tab 1 — "My Car"**: Contains the vehicle picker, garage, and parts list stacked vertically (full-screen scroll).
- **Tab 2 — "Interchange"**: Contains the part detail header and compatible vehicles table. Always accessible — shows the "Select a part" empty state before a part is chosen. Not visually disabled.

Selecting a part from the parts list automatically navigates to Tab 2. The active tab indicator uses `amber-500`. Tab bar is fixed to the bottom of the viewport.

---

## Component Breakdown

### `TopBar`
- App name/logo (left)
- `ActiveVehicleBadge` — shows "Year Make Model · Trim · Engine" in zinc-400 (human-readable strings from picker state, not IDs), or "No vehicle selected" when empty. Clicking it re-opens the picker.
- Feedback button (right) — opens `FeedbackModal`

### `LeftRail`
Contains three stacked sub-sections with a divider between each.

#### `VehiclePicker`
- Five cascading shadcn/ui `Select` dropdowns: Year → Make → Model → Trim → Engine
- Each dropdown is disabled and empty until the previous selection is made
- Human-readable labels (e.g. "2019", "Honda", "Civic") are captured from each dropdown's selected option at the time of selection, not derived from the API response from `GET /api/tree/cars`
- On full engine selection, call `GET /api/tree/cars?year_id=&make_id=&model_id=&trim_id=&engine_id=`. This returns a **list** — take the first element (`cars[0]`) as the resolved `Car` object. This is expected behavior; the combination of five IDs maps to exactly one car in practice.
- Two CTA buttons:
  - **"Set Active"** — dispatches `SET_ACTIVE_CAR`, collapses the picker, triggers parts load
  - **"Add to Garage"** — saves to garage without setting active or collapsing the picker
- When a vehicle is active, the picker collapses to a single line: `"2019 Honda Civic EX · 1.5T"` with a **"Change"** link that re-expands it and clears the active car

#### `Garage`
- List of `GarageCard` components — one per saved vehicle
- Empty state (no saved vehicles): a subtle placeholder — `"No saved vehicles. Add one above."` in zinc-400, centered
- Each card shows: `Year Make Model · Trim · Engine` (human-readable strings stored at save time)
- Card actions: **"Select"** (dispatches `SET_ACTIVE_CAR`, collapses picker) and a trash icon (dispatches `REMOVE_FROM_GARAGE`)
- Active vehicle card gets `border-l-2 border-amber-500` left accent
- Persisted as `JSON.stringify(GarageItem[])` in `localStorage` under key `pi_garage`
- `GarageItem` shape:
  ```ts
  interface GarageItem {
    id: number;          // Car.id from the API
    year: string;        // e.g. "2019"
    make: string;        // e.g. "Honda"
    model: string;       // e.g. "Civic"
    trim: string;        // e.g. "EX"
    engine: string;      // e.g. "1.5T"
  }
  ```

#### `PartsList`
- Visible only when a vehicle is active
- A single search input at the top (debounced 300ms). Typing uses `filterStr` on `POST /api/parts/parts` — **not** `GET /api/tree/search-parts` (which only searches `title` and lacks pagination). The POST endpoint searches across `title`, `description`, `part_number`, and `other_names`.
- `GET /api/tree/search-parts` is **not used** in this implementation.
- Scrollable list of `PartCard` components loaded via infinite scroll: on mount and on each scroll-to-bottom, call `POST /api/parts/parts`. Pagination state (`page`, `hasMore`) is local to the `useParts` hook, not in `AppContext`.
- **Pagination note:** the API uses 0-based page indexing on the client side. Send `page: 0` for the first request. The backend internally increments it before querying.
- Active part gets `border-l-2 border-amber-500`

**`PartCard`** shows:
- Part number — `amber-500`, `font-mono`, `text-sm`
- Title — `white`, `text-sm`
- Category label — `zinc-400`, `text-xs`. The category name is not returned directly from `POST /api/parts/parts` (only `category_id` is). Omit the category chip on `PartCard`; it is not worth a separate fetch per card.

Skeleton loader while fetching. Empty state: `"No parts found for this vehicle"`.

### `RightPanel`

#### `PartDetailHeader`
- Part number large (`text-2xl font-mono text-amber-500`)
- Title (`text-lg text-white`)
- Thumbnail image — rendered if `part.images` is a non-empty array. Use `image.url` as `<img src>` if present; otherwise prefix `image.bucket_path` with `/part-images/`. Caption comes from `part_image_text` on the `PartImages` join record. Clicking the thumbnail opens `ImageLightbox`.
- Metadata chips row (shadcn/ui `Badge` variant `outline`): positions, notes, replaces — only non-empty string fields rendered. Category is omitted (only ID available without an extra fetch).

#### `InterchangeTable`
- Filter input + row count badge (`"N compatible vehicles"`) inline above the table
- Filter value is sent as `filterStr` in the request body to `POST /api/parts/compatible_cars/:part_id`
- Full payload: `{ part_id, page, per_page, sort_col, sort_dir, filterStr }`
  - **Note:** `part_id` must appear in both the URL path and the JSON body — this is a backend requirement.
  - **Pagination note:** same 0-based convention as parts list — send `page: 0` for first request.
- Columns: Year · Make · Model · Trim · Engine — all sortable (click header to toggle asc/desc)
- Pagination state (`page`, `hasMore`, `sortCol`, `sortDir`, `filterStr`) is local to the `useCompatibleCars` hook
- Rows: `bg-slate-900`, `hover:bg-slate-800`, white text
- Currently active vehicle row (matched by `Car.id`) gets `bg-amber-500/10 border-l-2 border-amber-500`
- Load more: a **"Load more"** button at the bottom (shown only when `has_next` is true)

Empty state (no part selected): centered icon + `"Select a part from the list to see which other vehicles it fits."`

#### `FeedbackModal`
- Opens from the TopBar feedback button
- Fields: Name (optional), Email (optional), Comments (required — validate before submit, show inline error if empty)
- On submit: `POST /api/post-feedback/` (trailing slash required — Flask registers this blueprint at `/api/post-feedback/`)
- On 400 response: show field-level error from response body
- On success: close modal and show a success toast

#### `ImageLightbox`
- Modal overlay (`backdrop-blur-sm bg-black/70`)
- Full-size image with caption below
- Close on backdrop click or Escape key

---

## Data Flow

```
User selects Year
  → GET /api/tree/makes?year_id=
User selects Make
  → GET /api/tree/models?year_id=&make_id=
User selects Model
  → GET /api/tree/trims?year_id=&make_id=&model_id=
User selects Trim
  → GET /api/tree/engines?year_id=&make_id=&model_id=&trim_id=
User selects Engine
  → GET /api/tree/cars?year_id=&make_id=&model_id=&trim_id=&engine_id=
  → Take cars[0]; human-readable labels captured from picker state
  → Dispatch SET_ACTIVE_CAR, collapse picker

User types in parts search (debounced 300ms)
  → POST /api/parts/parts { car_id, page: 0, per_page: 30, filterStr, sort_col: '', sort_dir: 'desc' }
  → Resets list to page 0 on each new filter value

User scrolls to bottom of parts list
  → POST /api/parts/parts { ..., page: currentPage + 1 }  (if has_next)

User clicks a part card
  → Dispatch SET_ACTIVE_PART
  → POST /api/parts/compatible_cars/:part_id { part_id, page: 0, per_page: 30, sort_col: '', sort_dir: 'desc', filterStr: '' }
  → On mobile: auto-navigate to Tab 2

User sorts or filters interchange table
  → POST /api/parts/compatible_cars/:part_id { part_id, page: 0, per_page: 30, sort_col, sort_dir, filterStr }
  → Resets to page 0
```

---

## State Management

`AppContext` holds global navigation-level state only. Pagination, sort, and filter state is **local to each hook**.

```ts
interface AppState {
  activeCar: Car | null;       // resolved Car + human-readable label strings
  activePart: Part | null;
  garage: GarageItem[];
}

// Extended Car type stored in context includes resolved label strings:
interface ActiveCar {
  id: number;
  year: string;
  make: string;
  model: string;
  trim: string;
  engine: string;
}
```

Actions dispatched via `useReducer`:
- `SET_ACTIVE_CAR` — sets `activeCar`, clears `activePart`
- `SET_ACTIVE_PART`
- `ADD_TO_GARAGE` — adds to `garage`, syncs localStorage
- `REMOVE_FROM_GARAGE` — removes by `id`, syncs localStorage

On app init, `garage` is hydrated from `localStorage.getItem('pi_garage')`.

---

## API Surface Used

| Method | Path | Notes |
|---|---|---|
| GET | `/api/tree/years` | Returns `[{ id, name }]` |
| GET | `/api/tree/makes?year_id=` | Returns `[{ id, name }]` |
| GET | `/api/tree/models?year_id=&make_id=` | Returns `[{ id, name }]` |
| GET | `/api/tree/trims?year_id=&make_id=&model_id=` | Returns `[{ id, name }]` |
| GET | `/api/tree/engines?year_id=&make_id=&model_id=&trim_id=` | Returns `[{ id, name }]` |
| GET | `/api/tree/cars?year_id=&make_id=&model_id=&trim_id=&engine_id=` | Returns list; use `[0]` |
| POST | `/api/parts/parts` | `page` is 0-based; body: `{ car_id, page, per_page, sort_col, sort_dir, filterStr }` |
| POST | `/api/parts/compatible_cars/:part_id` | `page` is 0-based; `part_id` in both URL and body; body: `{ part_id, page, per_page, sort_col, sort_dir, filterStr }` |
| POST | `/api/post-feedback/` | Trailing slash required; body: `{ name, email, comments }` |

`GET /api/tree/search-parts` and `GET /api/parts/part/:id` are **not used** in this implementation.

---

## Error Handling

- API errors surface as a shadcn/ui `Sonner` toast — one-line message, auto-dismiss after 4s
- Cascade dropdowns that fail to load show an inline `"Failed to load — retry"` link
- Network failures on the interchange table show an inline error state with a retry button
- `FeedbackModal` shows inline field-level errors on validation failure or 400 response

---

## File Structure

```
ui-v2/
├── src/
│   ├── components/
│   │   ├── TopBar.tsx
│   │   ├── ActiveVehicleBadge.tsx
│   │   ├── LeftRail.tsx
│   │   ├── VehiclePicker.tsx
│   │   ├── Garage.tsx
│   │   ├── GarageCard.tsx
│   │   ├── PartsList.tsx
│   │   ├── PartCard.tsx
│   │   ├── RightPanel.tsx
│   │   ├── PartDetailHeader.tsx
│   │   ├── InterchangeTable.tsx
│   │   ├── ImageLightbox.tsx
│   │   ├── FeedbackModal.tsx
│   │   └── MobileTabBar.tsx
│   ├── context/
│   │   └── AppContext.tsx
│   ├── hooks/
│   │   ├── useVehicleTree.ts      (cascade dropdown state)
│   │   ├── useParts.ts            (parts list + infinite scroll)
│   │   └── useCompatibleCars.ts   (interchange table + sort/filter/pagination)
│   ├── lib/
│   │   ├── api.ts                 (typed axios wrappers for all endpoints)
│   │   └── garage.ts              (localStorage read/write helpers)
│   ├── types/
│   │   └── index.ts               (ActiveCar, Part, GarageItem, ApiPage, etc.)
│   ├── App.tsx
│   └── main.tsx
├── index.html
├── tailwind.config.ts
├── vite.config.ts
└── package.json
```

---

## Out of Scope

- User accounts or authentication
- Server-side garage persistence
- Part availability / pricing data
- Diagram image overlay (existing feature not carried forward in this phase)
- `GET /api/tree/search-parts` endpoint (superseded by `filterStr` on `POST /api/parts/parts`)
