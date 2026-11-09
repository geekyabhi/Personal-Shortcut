# Expenses Area (Dashboard · Charts · Splitwise) — Design Brief

> **Purpose of this document.** It describes the three pages of the **Expenses area** of
> "Personal Shortcut" completely — **Part A: Dashboard** (§0–§15), **Part B: Charts**, **Part C: Splitwise**, and
> **Part D: the components they share** — — every section, component, state, interaction and piece of
> data — so a designer (or Claude Design) can create a **better UI for it without losing any
> functionality**. It is organised as a design brief: product context → page anatomy →
> component inventory → flows → states → visual language → pain points → what must be kept.
>
> Everything here was taken from the real implementation
> (`dashboard.html` ~4,800 lines, `charts.html` ~2,900, `splitwise.html` ~1,150 — each one Django template with inline
> CSS + vanilla JS). Nothing is invented. Where something is *dormant*, *hidden* or *odd*, it says so.

---

# PART A — Dashboard (`/expenses/`)

## 0. TL;DR for the designer

| | |
|---|---|
| **What it is** | A personal finance area of three tabs — **Dashboard** (the ledger), **Charts** (analytics), **Splitwise** (shared-expense balances & import). The Dashboard is a personal finance ledger page: browse, filter, add, edit, bulk-edit, split and analyse your own expenses (Indian rupees, ₹). |
| **Who uses it** | One person at a time, mostly the owner on phone **and** desktop (it is an installable PWA). A second kind of user (an "expenses-only" account) sees the same page without Home/Splitwise. |
| **Scale** | ~3,100 expense rows for the main user. The whole list is loaded into the browser; filtering, grouping and totals all happen client-side. |
| **Core loop** | Pick a time period → (optionally) add filter rules → scan the list and the total → add/edit/delete/split entries. |
| **Hard constraints** | Must still run as a single server-rendered page with vanilla JS (no build step, no framework), keep **every** feature in §13, stay usable at 360 px wide, support light + dark theme. |
| **Biggest opportunity** | The page is feature-rich but visually flat and dense: one long scroll, ~10 equally-weighted controls in the list toolbar, the **total is buried below the list**, and power features (filter builder, bulk edit, Splitwise queue) are not discoverable. See §11. |

---

## 1. Product context

**App:** *Personal Shortcut* — a personal dashboard (Home, Expenses, Habits, Todos, Books, Blogs).
Part A covers **Expenses → Dashboard**; **Part B** covers **Charts**; **Part C** covers **Splitwise**; **Part D** lists what they share. Profile and Login are separate screens that use the same top bar and visual language (not detailed here).

**Data & currency:** every amount is rupees, formatted with Indian digit grouping and two
decimals (`1,23,456.00`), e.g. `₹` appears in the Add form label and the home-page widget.

**Users and jobs-to-be-done**

1. *"What did I spend this month / on X?"* — period + filters + a trustworthy total.
2. *"Log this expense now."* — fast add (name, amount, date/time, categories, source, mode).
3. *"Fix / clean up many rows."* — bulk edit, bulk insert.
4. *"Split a bill with friends."* — push an expense to Splitwise (one by one or queued in bulk).
5. *"Break one purchase into several categories."* — split an entry across categories.
6. *"Keep recurring payments honest."* — recurring mandates (subscriptions, rent) that auto-reconcile.
7. *"Find something specific."* — free-form filter builder or SQL-like query.
8. *"Get the data out."* — CSV export of the currently filtered list.

**Access levels (affects what the page shows):** the nav shows *Home* and *Splitwise* only for the
owner; "expenses-only" accounts see just *Dashboard* and *Charts*. Everything else on the page is identical.

---

## 2. Where the dashboard sits in the app

```
Login ──► Home (tiles) ─┬─► Expenses ─┬─ Dashboard   ← this brief
                        │             ├─ Charts      (separate page)
                        │             └─ Splitwise   (separate tab/page, owner only)
                        ├─ Habits / Todos / Books / Blogs   (owner only)
Account button (every page) ─► Profile page · Sign out
```

**Global top bar (present on every expenses page)**

- **Tab nav (pill group):** `Home` (owner only) · `Dashboard` · `Charts` · `Splitwise` (owner only). The current page is a gradient-filled pill.
- **≤ 640 px:** the pill group collapses into one **"Menu" button** showing the current page name; it opens a dropdown with the same links.
- **Account button (avatar):** round 38 px button — Google photo or the first letter of the name on a gradient. Opens a small card: name, email, **Profile**, **Sign out**.
- **Theme toggle:** round sun/moon button. Light/dark, remembered in the browser.

---

## 3. Dashboard page anatomy (top → bottom)

One centered column, max width **1400 px**, on a soft lavender page background with two blurred
gradient "orbs" floating in the corners. Sections in the exact order they appear:

```
┌──────────────────────────────────────────────────────────────────────┐
│ [Dashboard|Charts|…]  (Menu on mobile)             (● avatar) (☀)    │  ← 1 Top bar
├──────────────────────────────────────────────────────────────────────┤
│ ● Recent 2mo · ready  ● All expenses · 3105 rows  ● Splitwise · …    │  ← 2 Load-status chips
│ ● 3105 expenses loaded · fetched just now                [⟳ Refresh] │  ← 3 Data status bar
│ Expenses Dashboard   (hidden lock badge)                             │  ← 4 Page title
│ ┌─ Filters card ─────────────────────────────────────────────────┐   │
│ │ Period▾  Month▾/Year/Week/Day/Start–End   Sort by▾             │   │  ← 5 Filters
│ │ [Visual|SQL]   rule rows… [+ Add filter] [+ Add filter group]  │   │
│ │ (custom range presets)                      [ Apply Filters ]   │   │
│ └─────────────────────────────────────────────────────────────────┘   │
│ ┌─ 🔁 Recurring Mandates card ─────────────── [+ Add Mandate] ───┐   │  ← 6 Mandates
│ └─────────────────────────────────────────────────────────────────┘   │
│ ≡ Browse Expenses   [Detail view][Bulk edit][Bulk insert][CSV] [+Add]│  ← 7 List toolbar
│ ┌─ (Bulk insert panel, when open) ───────────────────────────────┐   │
│ ┌─ Expenses card ─────────────────────────── “17 of 3105” badge ─┐   │  ← 8 The list
│ │ (Splitwise queue bar)  (Bulk-edit bar)                          │   │
│ │ ▢ Title  [badge]                 ☑  ✎  🗑                      │   │
│ │   ₹ 450.00 · 2026-11-02 · 2:23 PM                               │   │
│ │ … scrolls inside a 620 px box, 40 rows at a time …              │   │
│ └─────────────────────────────────────────────────────────────────┘   │
│ ▮ Summary                                                            │  ← 9 Summary
│ ┌─ [Nov 2026]   Total · 17 entries          ₹ 12,345.00 ──────────┐  │
│ │ Group by ▾ → ranked bars                                         │  │
│ └──────────────────────────────────────────────────────────────────┘  │
│ ┌─ Biggest Transactions (top 10) ────────────────────────────────┐   │  ← 10 Top 10
│ └─────────────────────────────────────────────────────────────────┘   │
│ (Splitwise balances card — present in the markup but HIDDEN, see §11) │  ← 11 Dormant
└──────────────────────────────────────────────────────────────────────┘
 Floating: toasts (bottom), thin top-of-page loading bar, modals (centered)
```

---

## 4. Component inventory (every section, in detail)

### 4.1 Load-status chips ("background markers")
Three small pill chips under the top bar that show what is loading.

| Chip | Meaning |
|---|---|
| **Recent 2mo** | "Current + previous month — loads first" (the fast first paint) |
| **All expenses** | "Complete expense history" (loads in the background after the first paint) |
| **Splitwise** | "Splitwise groups & friends" — whether the Splitwise connection is available |

States / label suffix: *idle* (grey) · `· fetching…` (loading) · `· ready` or `· N rows` / `· 5 groups · 12 friends` (done) · `· failed` (red) · `· not connected` (Splitwise not configured).
*Design note:* these are developer-ish status indicators; a good redesign can fold them into one subtle status line or a skeleton state.

### 4.2 Data status bar (cache bar)
Hidden until the first load finishes. Content: green dot · text `"{N} expenses loaded[ (recent only)] · {cached|fetched} {just now | 12s ago | 3 min ago | 2h ago}"` · **Refresh** button (forces a re-fetch). The "ago" text updates every 60 s without refetching.

### 4.3 Page title + lock badge
`Expenses Dashboard` (gradient text). Next to it an **"unlocked"** badge with a lock icon, visible only while the hidden-categories lock is open; clicking it re-locks.

> **Hidden feature (keep undiscoverable).** Two private categories are masked everywhere
> (list, tags, group-by, top-10, filter value pickers) until unlocked. Unlock = tap the theme
> toggle or the "Browse Expenses" heading ~15 times quickly → a *"Verification required / Enter your
> access code"* modal (password field, Cancel/Confirm, shake + inline error on a wrong code).
> It is intentionally invisible; **do not add a visible affordance for it.** Unlock state lives
> in `sessionStorage`, and the theme toggle gets a green ring while unlocked.

### 4.4 Filters card
One card that drives **both** the list and the summary.

**Row A — period controls** (responsive grid: **1 column < 480 px, 2 columns ≥ 480 px, 3 columns ≥ 640 px**)

| Control | Options / behaviour |
|---|---|
| **Period** (select) | All Time · Yearly · **Monthly (default)** · Weekly · Daily · Custom Range |
| *contextual input* (only one shows) | Monthly → month picker (default = current month) · Yearly → number 2000–2099 · Weekly → ISO week picker · Daily → date picker · Custom → **Start date** + **End date** |
| **Sort by** (select) | Newest first (default) · Oldest first · Highest amount · Lowest amount |
| **Presets** (only for Custom) | Last 7 days · Last 30 days · Last 3 months · Last 6 months · Year to date — set the start/end dates |

**Row B — rule filters.** A **Visual | SQL** segmented toggle, then either:

- **Visual filter builder** — Notion-style. A list of **rule rows**: `[field ▾] [operator ▾] [value] (+ second value for "between") [✕]`. Rules can be wrapped in **groups** that are joined with **AND / OR** (each group has its own AND/OR selector, a remove-group ✕, and can nest), so you can express `(Category includes Food OR Category includes Dining) AND Amount > 500`. Buttons: **+ Add filter**, **+ Add filter group**, **Clear**. Half-filled rules are ignored (no error). The rule tree is **saved in the browser** and restored next visit. Rules apply **live** as you edit (no Apply needed).
  - **Fields (15):** Name (text) · Amount (number) · Date (date) · Category (multi) · Source (select) · Mode (select) · Comment (text) · Other partner (text) · Splitwise ID (number) · Processed / Add to Split / From Split / Split Added / Is Mandate / Recurring (checkboxes).
  - **Operators by type:**
    - text: contains · doesn't contain · is · is not · is empty · is not empty
    - number: = · ≠ · > · < · ≥ · ≤ · between · is empty · is not empty
    - date: is on · is before · is after · is between · is empty · is not empty
    - select: is · is not · contains · is empty · is not empty
    - multi (categories): includes · doesn't include · is only · is empty · is not empty
    - checkbox: is checked · is unchecked
  - Value inputs adapt: dropdown of known categories/sources, datalist for modes, date picker, number input.
- **SQL mode** — a monospace textarea (3 rows) with an **Apply query** button, a hint line, and an inline red error line. Example: `amount > 500 AND (category = 'Food' OR category = 'Travel')`. Supports `= != <> > < >= <=`, `BETWEEN a AND b`, `LIKE` / `CONTAINS`, `IS [NOT] NULL`, `IS [NOT] TRUE/FALSE`, `NOT`, `AND`, `OR`, parentheses. Column names/aliases: `name, amount, date, category, source, mode, comment, partner, splitwise_id, processed, add_to_split, from_split, split_added, mandate, recurring`. Switching to SQL shows the current visual rules converted to SQL; both modes edit the same rule tree.

**Apply Filters** (primary pill button): re-fetches the list for the chosen **period + sort** (these two go to the server; the rule filters are client-side). The button disables while loading.

### 4.5 Recurring Mandates card
Title **"🔁 Recurring Mandates"** + primary **+ Add Mandate** button. Body = list of mandate rows (same row style as expenses): **title**, **amount**, then `Monthly · 2026-08-01 → ongoing` (frequency · start → end or "ongoing"), with **edit** and **delete** icon buttons. Empty state: *"No recurring mandates yet."* Loading: *"Loading…"*. Error: *"Failed to load mandates: …"* / *"Network error loading mandates."*
A mandate is a **template**, not a transaction: it never appears in the expense list or totals. Its generated **occurrences** are normal expense rows flagged "Recurring".
Frequencies: Weekly · Monthly · Quarterly · Yearly.
→ On every dashboard load the app checks for missed occurrences and may open the **Mandate check-in modal** (§5.5).

### 4.6 List toolbar ("Browse Expenses")
Left: section heading with list icon — **Browse Expenses** (also a hidden 15-tap target, see 4.3).
Right: a button group + primary action. **Every button is an icon-only round button (≈ 2.4 rem) that expands on hover / keyboard focus into a 9.5 rem gradient pill revealing its label** (the label is invisible until then; `aria-label` is always present). On touch devices there is no hover, so the labels are effectively never visible — see §11 #4.

| Button | Style | What it does |
|---|---|---|
| **Detail view** | ghost; becomes primary + "Exit detail view" when on | Shows extra tags & the comment on every row. (Clicking a row opens the **Detail modal** in *any* view, not only this one.) |
| **Bulk edit** | ghost; primary + "Exit bulk edit" when on | Turns the rows into inline editable forms (§4.9). |
| **Bulk insert** | ghost; primary + "Close bulk insert" when on | Opens the multi-row "add many" panel (§4.8). |
| **Export CSV** | ghost | Downloads the **currently filtered** list as `expenses-YYYY-MM-DD.csv` (columns: Title, Amount, Date, Time, Categories, Source, Mode). |
| **Add Expense** | primary pill | Opens the Add/Edit modal (§5.1). |

Detail view and Bulk edit are **mutually exclusive** (turning one on turns the other off). Bulk insert is independent.

### 4.7 Loading / error / empty for the list
- **Skeleton:** four grey shimmering rows (`.sk-line`) while the first load runs.
- **Error box:** red box with the message (*"Network error: …"* or the server's error).
- **Empty:** *"No expenses match your filters."*
- **Top loader:** a thin gradient progress bar fixed to the top of the viewport during any fetch/save.

### 4.8 Bulk insert panel
A card above the list with header **"Bulk insert — N rows"** and buttons **+ Add row**, **Create N expenses** (disabled until valid), **Close**. Starts with 3 blank rows. Each row (same grid as bulk edit): **Name · Amount · Date (default today) · Time (default now) · Category pills (multi, + type-to-add new) · Source (searchable combobox) · Mode · Comment · Other partner · Splitwise ID · checkboxes Processed / Add to Split / From Split / Split Added · remove-row ✕**. Rows missing name/amount/date are outlined red and skipped (toast: *"N row(s) need a name, amount and date"*). Creating shows a saving state on each row.

### 4.9 The expense list (the main component)
A card titled **Expenses** with a **count badge** (`17 results` or `5 of 3105` when rule-filters narrow it). The list is a scroll container (**max-height 620 px; 68 vh on phones**) that shows **40 rows at a time** and loads more on scroll; a footer line says *"40 of 213 shown — scroll for more"* / *"all 213 shown"*. Rows animate in with a small stagger.

**Standard row anatomy**

```
 Title [split badge]                                   ☑   ✎   🗑
 ₹ 1,299.00
 2026-11-02 · 2:23 PM
 (Detail view only:) tags: categories · source · mode · partner · Splitwise ID #… · ✓ processed · flags…
 (Detail view or split-flagged:) 💬 comment text
 (If flagged to split, not yet split:) [ Split on Splitwise ]  → inline panel
```

- **Title** (bold) — empty titles render as `—`.
- **Amount** — Indian-grouped, 2 decimals.
- **Date · time** — time only if one was recorded. The time shown is the *entered wall-clock time* (not converted to the viewer's time zone).
- **Split badge:** `to split` (pending, flagged but not done) · `● queued` (staged in the Splitwise queue) · `✓ split added` (done).
- **Row actions:** a **checkbox** = *Processed* (toggles instantly; a "Processed = false" filter drops the row immediately), **edit** pencil → Add/Edit modal, **delete** trash → Delete modal.
- **Clicking anywhere on a row** (except its buttons, checkbox or split panel) opens the **Detail modal** (§5.3); rows highlight with a faint indigo tint on hover to signal this.
- Rows are visually marked processed vs unprocessed (`proc` / `unproc` classes) and dim to ~55 % opacity with a loader while saving.
- **Detail view tags:** category tags (indigo), source/mode/partner/Splitwise-ID tags (grey), `✓ processed` / `○ unprocessed`, `add to split`, `⇦ from split`, `✓ split added` / `○ split not added`.

**Inline "Split on Splitwise" panel** (only on rows flagged *Add to Split* and not yet split; the button reads **Edit queued split** if already staged)
- Loads Splitwise data once (groups + friends). If not configured: red text *"Splitwise isn't configured."*
- **Group select:** *Individual (friends, no group)* or one of your groups.
- **People list:** a checkbox + an amount field per person. By default the amount is divided equally; the first person absorbs rounding. Typing an amount **locks** that person; the remainder is redistributed across unlocked people. You can untick yourself (then you "owe nothing"; your share is sent as 0).
- **Live total:** `Shares: ₹300.00 / ₹300.00 ✓` (green) or `· must match total` / `· pick at least 1 other person` (red). Buttons: **Save to queue** and **Push now**, both disabled until the shares add up.
- Last used group and members are remembered.
- **Queue bar** (appears above the list when anything is staged): a count badge, text `"3 splits queued · ₹1,240.00"`, a progress bar while pushing, **Push all queued**, **Clear queue** (asks for confirmation). Staged items persist in the browser.
- **After a successful push** the server: sends the split to Splitwise, **reduces the row's amount to your share**, prepends the breakdown to the comment, and ticks *Split Added*. Toast: *"Pushed to Splitwise · amount set to your share (₹…)"*.

**Bulk-edit row** (replaces the standard row while *Bulk edit* is on): inline inputs for name, amount, date, categories (pill/comma list), source, mode, comment, other partner, Splitwise ID and the five flag checkboxes. Edited rows get a **dirty** highlight. A bar above the list shows **"Bulk edit — N changed"** with **Save changed** (disabled until something changed) and **Exit** (discards unsaved edits). Only the rows loaded so far are editable (*"editing first 40 of 213 — exit bulk edit to load more"*). Inside bulk edit each row can also stage a **category split** (shown as a "split staged" summary) that executes on *Save changed*. Saves run in parallel in the background with per-row loaders; failures are reported and re-staged.

### 4.10 Summary section
Heading **Summary** (chart-bar icon). It always reflects the *filtered* set (period + rules), **including when empty**.
- **Period badge** (gradient pill) — `All Time`, `2026`, `2026-11`, `2026-11-02 – 2026-11-08` etc.
- **Total** (label) with `· 17 entries` and the **big gradient total** (`clamp(1.6rem, 5vw, 2.2rem)`, thin weight).
- **Group by** select (max 220 px wide): None · Category · Source · Mode · Day · Week · Month · Year.
- **Ranked list** when grouped: rank number · name · thin gradient bar (proportional) · amount (indigo) · `% of total` · count. Category/source/mode are sorted by amount (desc); Day/Week/Month/Year are sorted **chronologically** with friendly labels (`Nov 2026`, `2 Nov – 8 Nov`). Categories honour the hidden-category lock.
- Loading: 4-line skeleton. Error: red box.

### 4.11 "Biggest Transactions"
Card with the **top 10** entries (by amount) within the current filter: title, date·time + category/source tags, amount at right. Empty: *"No entries found."*

### 4.12 Dormant "Splitwise" card (do not design around it)
The page markup contains a hidden section (**You owe / You're owed / Net** + "Recent activity" + Refresh). It is `display:none` and its Refresh handler is not implemented — it is a leftover from before the dedicated Splitwise tab. **Safe to drop** — the Splitwise tab (Part C) covers it.

---

## 5. Modals and overlays

All modals: centered card over a dimmed backdrop, close on backdrop click/Escape where noted, inputs with pill or 12 px radii, primary **gradient pill** confirm button + ghost cancel.

### 5.1 Add / Edit Expense (also Add / Edit Mandate)
Title: *Add Expense* · *Edit Expense* · *Add Mandate* · *Edit Mandate*.

| Field | Type | Notes |
|---|---|---|
| Name | text, required | placeholder "e.g. Groceries"; autofocus |
| Amount (₹) | number, required | step 0.01, min 0 |
| Date & time | datetime-local | required for new entries; defaults to *now*; on edit it's only sent if changed |
| Categories | **pill multi-select** | all known categories as toggle pills + an inline **"+ new category"** input (Enter or + to add) |
| Source | searchable combobox | scrollable dropdown filtered as you type; can add a new value |
| Mode | searchable combobox | UPI / Card / Cash… learned from existing data |
| Comment | textarea (3 rows) | "Notes…" |
| Other Partner | text | |
| **This is a recurring mandate** | checkbox | reveals **Frequency** (Weekly/Monthly/Quarterly/Yearly), **Start date** (required), **End date** (optional) |
| Flags | 5 checkboxes | Add to Split · From Split · Split Added · Processed · Recurring occurrence |
| Splitwise ID | number | "advanced; clear to allow re-import" |
| *Also split on Splitwise* | collapsible | group select + member checkboxes; "splits equally between you and the people you tick; you are recorded as the payer" |
| *Split across categories* | link-button | only when editing a normal expense → opens §5.4 |

Inline red error line (*"Name is required."*, *"Amount is required."*, *"Date is required."*, *"Start date is required for a recurring mandate."*). Buttons **Cancel / Save**. **Save closes the modal immediately** and finishes in the background with a row loader (optimistic UI).

### 5.2 Delete confirmation
Red trash icon · **"Delete Expense?"** · *"You're about to delete **{name}**. This will permanently delete it and cannot be undone."* · **Cancel / Delete**. The button shows *"Deleting…"*. The row disappears locally without a reload. (The same modal deletes mandates.)

### 5.3 Detail modal
Opened by clicking any row (in any view). Close ✕. Big **title** (+ split badge) and **amount**, then a two-column key/value grid: Date · Source · Mode · Categories · Comment · Other Partner · Splitwise ID · Processed · Add to Split · From Split · Split Added (empty values shown as `—`). Actions: **Close · Edit · Delete** and a **Split across categories** link.

### 5.4 Split across categories
Title *Split "{name}"*. Sub-text: *"Total to allocate: ₹… — every split needs a name, category, and amount, and they must add up to the total."* A list of split rows, each with: **name**, **category** (searchable combobox, add-new), **amount**, and a "more" expander holding source, mode, comment, other partner, and flag checkboxes (each defaults to the original entry's value). An optional per-row **Splitwise** sub-panel appears when *Add to Split* is ticked. **+ Add another category**. A live **"remaining"** line shows what's left to allocate. Buttons **Cancel / Split**. Result: the original entry is replaced by one entry per split (same date/time), each annotated *"Split i/n of '…' — total … on …"*. From Bulk edit the split is only **staged** and runs on *Save changed*.

### 5.5 Mandate check-in
Opened automatically on load when recurring payments have missed cycles. Title **"🔁 Recurring mandates need a check-in"**; explainer: *"These haven't been logged for a while. For each, say whether it's still running (we'll backfill through today) or it ended (pick the date — nothing beyond it gets created)."* One row per mandate: title, `Monthly · ₹199.00 · 3 missed: 2026-09-01, 2026-10-01, …`, radio **Still running / Ended**, and a date picker (≤ today) when *Ended*. Buttons **Not now** (asks again next load) / **Confirm & backfill** (toast *"Backfilled 5 expenses"*).

### 5.6 Unlock modal — see 4.3.
### 5.7 Toasts
Bottom-stack, auto-dismiss (3 s default; longer for warnings). Types: **success** (green, ✓), **error** (red, ✕), **info** (blue, ℹ). Examples: *"Expense deleted"*, *"Marked processed"*, *"Filter applied"*, *"Added to Splitwise queue"*.

---

## 6. Key user flows (step by step)

1. **Review a month (default).** Page loads on *Monthly = current month* → Recent chip loads first (fast paint) → All-expenses loads silently and overwrites → list + total render. Change month → **Apply Filters**.
2. **Add an expense.** *Add Expense* → fill name/amount (date defaults to now) → tap category pills → Source/Mode → **Save** (modal closes instantly; the row appears with a subtle loader, then settles).
3. **Mark processed.** Tick the checkbox on a row; it saves immediately; if a "Processed = false" rule is active the row vanishes.
4. **Narrow with rules.** Add filter → `Category includes Food` → `+ Add filter` → `Amount > 500` (live). Or switch to **SQL** and type the same. The count badge becomes "12 of 213"; the Summary and Top-10 follow.
5. **Group the spend.** Summary → *Group by Category* → ranked bars; or *Month* for a chronological breakdown.
6. **Bulk clean-up.** *Bulk edit* → change several rows → **Save changed**.
7. **Add many.** *Bulk insert* → fill rows → **Create N expenses**.
8. **Split a bill.** Flag a row *Add to Split* → **Split on Splitwise** → pick group + people → **Save to queue** (repeat for others) → **Push all queued** *or* **Push now** on a single row.
9. **Split across categories.** Row → Detail or Edit → **Split across categories** → allocate amounts → **Split**.
10. **Recurring payment.** *+ Add Mandate* (frequency + start) → later the **check-in** modal offers to backfill missed cycles → real expense rows appear in the list.
11. **Export.** Filter to what you want → **Export CSV**.

---

## 7. Data shown in the UI (what each expense contains)

| Field | Type | Shown / edited as | Notes for layout |
|---|---|---|---|
| `title` | text | row title | can be long; empty → `—` |
| `amount` | number (2 dp) | `1,299.00` | right-weighted, largest text in a row |
| `date` | `YYYY-MM-DD` | row meta | the entry's own calendar day |
| `datetime` | ISO with offset | time `2:23 PM` | optional; show wall-clock time |
| `categories` | string[] (0..n) | tags / pills | none → counted as "Uncategorized"; can be several |
| `source` | text (first of `sources`) | tag / combobox | e.g. card/bank/wallet name; dozens of distinct values |
| `mode` | text | tag / combobox | UPI · Card · Cash … (~9 values) |
| `comment` | text | 💬 block | multi-line; may contain Splitwise breakdowns |
| `other_partner` | text | tag | |
| `add_to_split`, `from_split`, `split_added`, `processed` | bool | badges / checkboxes | drive the split badge + checkbox |
| `splitwise_id` | number | tag "Splitwise ID #…" | unique; "advanced" field |
| `is_mandate`, `mandate_frequency`, `mandate_start`, `mandate_end` | mandate template fields | Mandates card | templates only |
| `recurring` | bool | flag | marks a generated occurrence |

Realistic extremes to design for: **3,100 rows**; **~40 categories**, **~40 sources**; titles up to 500 chars; 700 uncategorized rows; amounts from ₹0 up to lakhs (`3,01,907.00`); a month with 0 entries; a filter that matches nothing.

---

## 8. State catalogue (every state a designer should account for)

| Area | States |
|---|---|
| Page load | initial skeleton → *recent* painted → *all* painted (silent swap) |
| Chips | idle · loading · done · error · "not connected" |
| Data bar | hidden · "loaded/cached/fetched N ago" · refreshing (button shows "…") |
| List | loading skeleton · populated · empty ("No expenses match your filters.") · error · "scroll for more" · "all shown" |
| Row | normal · processed/unprocessed · saving (dim + loader) · to-split · queued · split-added · dirty (bulk edit) · split-staged (bulk edit) · invalid (bulk insert, red outline) |
| Modes | normal · Detail view · Bulk edit · Bulk insert open |
| Buttons | default · hover (lift) · active (press) · disabled · "pushing…/deleting…/backfilling…" |
| Filters | none · active rules (count badge) · SQL parse error (inline) · half-built rule (ignored) |
| Summary | empty · populated · grouped · loading · error |
| Lock | locked (default) · unlocked (badge + ring) |
| Splitwise | not configured · loading · ready · queue empty/non-empty · pushing with progress |
| Theme | light · dark (full dark palette) |

---

## 9. Responsive behaviour today

Mobile-first CSS with breakpoints at **480, 560, 600, 640, 768 px**.

- **< 480 px:** filter grid is 1 column. **≥ 480 px:** 2 columns, card padding grows (1.25 → 1.5 rem), radius 22 px. **≥ 640 px:** 3 columns.
- **≤ 640 px:** tab pills → "Menu" dropdown.
- **≤ 600 px:** the three load-status chips **stack one per line** (full width, tiny 0.62 rem text), the data-status bar wraps, row padding and action buttons shrink (28 px), the list becomes **68 vh** tall, the Splitwise queue bar puts its progress bar on its own row, and modals get a 0.6 rem margin with `max-height: 92vh`.
- **≥ 768 px:** more body padding (2.5 rem / 1.5 rem).
- Toolbar buttons are icon-only at every size (labels appear only on hover/focus).
- Body padding 0.75 rem → 1.25 rem → 1.75 rem. Container max width 1400 px.
- `prefers-reduced-motion` is honoured (animations effectively disabled).
- The page is an **installable PWA** (manifest + service worker), so phone use is a first-class case.

---

## 10. Current visual language (so you can keep, or deliberately change, it)

**Mood:** soft, airy "glassmorphism" on a lavender background with indigo→violet gradients, pill-shaped controls, gentle shadows, floating blurred orbs.

| Token | Value |
|---|---|
| Font | **Inter** (400–900), system fallbacks; monospace (SF Mono) for the SQL box |
| Accent | `#4F46E5` (indigo) → `#7C3AED` (violet); gradient `135deg` |
| Soft gradient | `#EEF2FF → #F5F3FF` |
| Page bg (light) | `#F5F4FA`; text `#111827`; muted `#6B7280` / `#9CA3AF`; borders `#E5E7EB` / `#F3F4F6` |
| Dark mode | page `#0F0F14`, surfaces ≈ `#1B1B28` / `rgba(255,255,255,0.04–0.08)`, text `#F9FAFB`, muted `#9CA3AF` |
| Success / danger | `#10B981` / `#059669` · `#EF4444` / `#DC2626`; tinted backgrounds `#ECFDF5`, `#FEF2F2` |
| Cards | `rgba(255,255,255,0.75)` + `backdrop-filter: blur(16px)`, 1 px white border, **radius 20 px** (22 px ≥ 480), shadow `0 4px 24px rgba(0,0,0,.06)`, **lift −4 px on hover** |
| Buttons | **100 px pill**; primary = gradient + indigo glow; ghost = outlined/glass; icon buttons 38 px round |
| Inputs | 8–12 px radius (selects/inputs), pill for comboboxes in bulk rows |
| Tags | small pills: category = indigo 10 % tint; source/mode = grey; flag-off = muted |
| Radii in use | 8 (most), 12, 20, 100 (pills), 50 % (round) |
| Motion | card/section **fade-up** on scroll with 80 ms stagger (max 400 ms); rows stagger in; hover lift with spring easing `cubic-bezier(.34,1.56,.64,1)`; orbs float 9–11 s; top loader bar; toast pop-in |
| Icons | inline **Feather-style stroke icons** (no icon font, no external requests) |
| Big numbers | total uses a **thin (400)** weight gradient text |
| Page title | `clamp(1.5rem, 5vw, 2rem)`, weight 500, gradient text |

Sibling pages (Login, Profile, Home) use the same card/orb/gradient/pill language — a redesign should stay consistent with them or propose updating all together.

---

## 11. Pain points & opportunities (observed, not invented)

Ranked roughly by impact. These are starting points, not requirements.

1. **The answer to "how much?" is at the bottom.** The total and breakdown sit *below* a 620 px scrolling list. Consider a sticky/at-top summary strip (period · total · count · quick group-by) that always reflects the filter.
2. **Filters card is heavy and always open.** Period + sort + a full query builder + presets + Apply stack into a tall block before any data. Consider a compact period switcher (prev/next month arrows, quick chips: This month · Last month · YTD · Custom), with the rule builder behind a "Filters" popover/drawer showing active-filter chips.
3. **Two "Apply" models.** Period/sort need **Apply Filters**; rules apply **live**. Users can't tell which is which. Unify (auto-apply with debounce, or clearly mark pending changes).
4. **List toolbar overload and hidden labels.** Five equally-weighted icon-only buttons (Detail, Bulk edit, Bulk insert, Export, Add) whose labels only appear on hover — invisible on phones, so first-time users can't tell what they do. Primary action = Add; the rest are secondary/tertiary → move into a "⋯"/"Tools" menu or a segmented "View: Compact / Detailed / Edit" control. *Detail* and *Bulk edit* are mutually exclusive modes and should read as one control.
5. **List is a nested scroller inside a scrolling page** (620 px box) — awkward on phones (scroll-trap). Consider page-level scrolling with sticky headers, virtualisation, or date-grouped sections ("Today / Yesterday / 12 Nov") with per-day subtotals.
6. **Rows are dense and flat.** Title, amount, date, badges and three actions share one tight block; category/source are hidden unless Detail view is on. Consider a two-line layout: title + amount on line 1, date · category chip · source on line 2; swipe actions on mobile; checkbox semantics ("Processed") need a label/tooltip because it's ambiguous.
7. **No visual encoding of amount or category.** Category colour dots, an amount bar, or an inline sparkline would make scanning easier. No chart appears on this page at all (charts live on a separate tab) — a small spending-over-time or category-donut next to the total would help.
8. **Power features are undiscoverable.** Filter groups (AND/OR), SQL mode, bulk edit, the Splitwise queue, category split and the mandate check-in have no onboarding or empty-state hints.
9. **Mandates card competes with the list** for prime position though it is rarely used. Collapse by default; show a badge when something needs attention.
10. **Developer-ish chrome.** The three load-status chips and the "cached/fetched" bar expose implementation details. Replace with a single quiet "Updated just now · ⟳".
11. **Modal-heavy editing.** Add/Edit is a long scrolling form (15+ fields). Consider progressive disclosure: name/amount/date/category up front; source/mode/comment/partner/flags/Splitwise under "More".
12. **Inconsistent terminology & micro-copy.** "Processed", "Mode", "Source", "Other Partner", "Add to Split / From Split / Split Added" are internal terms — add helper text or rename (e.g. "Reviewed", "Paid via", "Paid with", "Shared with").
13. **Splitwise flow is cognitively heavy** (inline panel + queue + remembered prefs + per-row push). A dedicated "Split" drawer with a clear stepper and a persistent queue tray would clarify it.
14. **Accessibility gaps to fix in a redesign:** colour-only state (processed/unprocessed), small 0.72 rem text, many icon-only buttons, modals without documented focus-trap, low-contrast greys (`#9CA3AF` on white), gradient text for the total (contrast).
15. **Dormant code/UI:** the hidden Splitwise balances card and several stale internal names can be removed.

---

## 12. Suggested design goals (to give Claude Design)

1. **Answer first.** Total + period + trend visible without scrolling, on mobile too.
2. **Fast capture.** Add an expense in ≤ 3 taps/fields (name, amount, category) with smart defaults (today, last-used source/mode).
3. **Calm density.** Keep the data-rich feel, but with clear hierarchy, grouping by day, and consistent chips.
4. **Progressive power.** Simple by default; filters, bulk ops, splits and mandates reachable but tucked away with good empty-state guidance.
5. **Mobile-first.** Thumb-reach primary action (FAB or bottom bar), swipe/long-press row actions, bottom sheets instead of centered modals.
6. **Trust.** Clear saving/saved/failed feedback, undo for delete (today delete is permanent), never lose queued work.
7. **One visual system** shared with Home/Login/Profile/Charts, light + dark.

---

## 13. Functional checklist — everything the redesign must still do

Use this as the acceptance list. Nothing here may be dropped (except §4.12).

**Navigation & shell**
- [ ] Tab nav (Home*, Dashboard, Charts, Splitwise*) with mobile collapse; \*owner only
- [ ] Account button → Profile, Sign out · theme toggle (light/dark, persisted)
- [ ] Toasts · top loader bar · skeletons · error boxes

**Data loading**
- [ ] Fast first paint of recent data, then full history swap; manual **Refresh**; "loaded N · fetched … ago" status
- [ ] Splitwise connection status (configured / not)

**Filtering**
- [ ] Period: All / Yearly / Monthly / Weekly (ISO) / Daily / Custom, with matching inputs; custom presets (7d, 30d, 3m, 6m, YTD)
- [ ] Sort: newest, oldest, highest, lowest
- [ ] Rule builder with 15 fields, typed operators, nested AND/OR groups, live apply, persisted; SQL mode (parse ⇄ visual), errors inline
- [ ] Count badge `N results` / `N of M`

**Browsing**
- [ ] Lazy list (40 at a time), empty/error/loading states
- [ ] Row: title, amount (₹, Indian grouping), date + optional time, split badge, processed toggle, edit, delete
- [ ] Detail view (extra tags/comment, inspect modal) · Bulk edit (dirty tracking, save/exit, staged splits) · Bulk insert (N rows) · CSV export of filtered list

**Create / edit / delete**
- [ ] Add/Edit form with all fields in §5.1 incl. category pills + add-new, searchable Source/Mode, mandate fields, flags, Splitwise ID
- [ ] Optimistic save with per-row loader; delete confirm (permanent); delete from local state without reload

**Splitting**
- [ ] Split across categories (amounts must sum; trace note; same date/time) — direct or staged in bulk edit
- [ ] Splitwise: group/individual, per-person shares with lock + auto-balance, opt-out of own share, save-to-queue, push now, push-all with progress, clear queue, remembered selections; after push → amount becomes your share, Split Added ticked, breakdown in comment

**Mandates**
- [ ] List (frequency · start → end/ongoing), add/edit/delete; check-in modal with Still running / Ended + cutoff; backfill creates real rows; templates excluded from list/totals

**Analysis**
- [ ] Summary: period badge, total, entry count, group-by (category/source/mode/day/week/month/year), ranked bars with %/count, chronological date groups
- [ ] Biggest transactions (top 10)

**Privacy**
- [ ] Hidden-category lock (masked everywhere until unlocked; invisible entry point; session-scoped unlock)

---

## 14. Technical constraints for the new design

- **Stack:** Django server-rendered template; **vanilla JS, no framework, no bundler, no build step**. Fonts load from Google Fonts; icons are inline SVG; Chart.js (if used) comes from a CDN. Keep it a single HTML template (+ inline or static CSS/JS) that Django can serve.
- **No server-side pagination/aggregation on this page:** the client fetches the whole filtered-by-period list once and does the rest (rules, summary, grouping, top-10, CSV) in the browser. Designs that need server aggregates would require new endpoints.
- **Theming:** `data-theme="dark"` on `<html>`, toggled by script, remembered in `localStorage` (`ps_theme`); pages read it in `<head>` before paint to avoid flash. Provide both palettes.
- **Browser storage used today:** `ps_dash_filters` (rule tree), `ps_split_queue` (staged Splitwise pushes), `ps_category_split_queue` (staged category splits), `ps_split_prefs` (last Splitwise group/members), `ps_theme`; `sessionStorage.exp_unlocked` (hidden-category unlock).
- **Currency/locale:** `en-IN` number formatting, 2 decimals.
- **Security:** user-entered text must be escaped when rendered (titles, comments, tags).
- **Auth:** the page requires a signed-in session; owner vs expenses-only access flag (`restricted`) hides Home/Splitwise.

### 14.1 API the page uses (for reference; no backend change is required)

| Purpose | Request |
|---|---|
| Load list (period + sort; `all=1` = everything) | `GET /expenses/list/?period=monthly&month=2026-11&sort=date_desc&all=1` |
| The person's own categories / sources / modes for the pickers | `GET /expenses/options/` (add: `POST /expenses/options/{categories|sources|modes}/`; rename: `PATCH …/{id}/`; delete: `DELETE …/{id}/`) — saved per account, new values are saved automatically when an expense is saved |
| Create | `POST /expenses/create/` |
| Update (incl. processed toggle) | `PATCH /expenses/{id}/update/` |
| Delete | `DELETE /expenses/{id}/delete/` |
| Split across categories | `POST /expenses/{id}/split/` |
| Push to Splitwise | `POST /expenses/{id}/push-split/` |
| Splitwise groups/friends | `GET /expenses/splitwise/overview/` |
| Mandates: list / pending check-in / backfill | `GET /expenses/mandates/` · `GET /expenses/mandates/reconcile/` · `POST /expenses/mandates/{id}/backfill/` |

Entry JSON shape returned by the list: `page_id, title, amount, date, datetime, categories[], source, sources[], mode, comment, other_partner, add_to_split, from_split, split_added, processed, splitwise_id, is_mandate, mandate_frequency, mandate_start, mandate_end, mandate_id, recurring`.

---

## 15. Appendix — current copy (microcopy) inventory

**Headings:** Expenses Dashboard · Browse Expenses · Expenses · Summary · Biggest Transactions · 🔁 Recurring Mandates · Verification required · Delete Expense? · Add/Edit Expense · Add/Edit Mandate · Split "{name}" · 🔁 Recurring mandates need a check-in.
**Buttons:** Apply Filters · Apply query · + Add filter · + Add filter group · Clear · Refresh · Detail view / Exit detail view · Bulk edit / Exit bulk edit · Bulk insert / Close bulk insert · Export CSV · Add Expense · + Add Mandate · + Add row · Create N expenses · Save changed · Exit · Save · Cancel · Delete · Close · Edit · Split · + Add another category · Split on Splitwise / Edit queued split · Save to queue · Push now · Push all queued · Clear queue · Not now · Confirm & backfill · Confirm.
**Empty / helper text:** "No expenses match your filters." · "No entries found." · "No recurring mandates yet." · "No conditions yet." · "Loading…" · "{N} of {M} shown — scroll for more" · "all {N} shown" · "queue empty".
**Errors:** "Name is required." · "Amount is required." · "Date is required." · "Start date is required for a recurring mandate." · "Network error: …" · "Splitwise isn't configured." · "Row not found — reload the list." · "Splits add up to ₹X, but the original expense is ₹Y." · "Every split needs a name, category, and amount." · "Incorrect code. Try again."
**Confirmations / toasts:** "Expense deleted" · "Marked processed" / "Unmarked processed" · "Filter applied" / "Filters cleared" · "Added to Splitwise queue" · "Pushed to Splitwise · amount set to your share (₹…)" · "Backfilled N expenses" · "N row(s) need a name, amount and date".
**Status strings:** "Recent 2mo · fetching… / ready / failed" · "All expenses · N rows" · "Splitwise · N groups · M friends / not connected" · "N expenses loaded (recent only) · cached/fetched 2 min ago".
**Detail labels:** Date · Source · Mode · Categories · Comment · Other Partner · Splitwise ID · Processed · Add to Split · From Split · Split Added.
**Tags:** `to split` · `● queued` · `✓ split added` · `✓ processed` · `○ unprocessed` · `add to split` · `⇦ from split` · `○ split not added`.

---
---

# PART B — Charts page (`/expenses/charts/`)

> Source: `expenses/templates/expenses/charts.html` (~2,900 lines, Chart.js 4.4.3 + hammer.js + chartjs-plugin-zoom from a CDN).
> The Dashboard answers *"what are my transactions?"*; **Charts answers *"what is my spending doing over time?"***
> Unlike the Dashboard, the **server aggregates** the data here (chart, category-timeseries, heatmap endpoints) and the page **loads automatically** when opened.

## B.1 Layout (top → bottom)

```
┌──────────────────────────────────────────────────────────────────────┐
│ [Home|Dashboard|Charts*|Splitwise]               (● avatar)  (☀)     │ 1 Top bar (shared)
│ ● 3105 expenses loaded · fetched just now             [⟳ Refresh]    │ 2 Data status bar
│ Expense Charts                                                       │ 3 Title
│ ┌─ Filters card ───────────────────────────────────────────────────┐ │
│ │ Period▾  Breakdown▾  Bucket by▾  (Month/Year/Week/Day/Start–End)  │ │ 4 Filters
│ │ (presets)  [filter rule rows…]               [ Apply Filters ]    │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│ ( ◌ Loading expenses… )   (error box)                                │ 5 Loading / error
│ ┌ [Nov 2026]  Grand Total  ₹ 12,345.00 ───────────────────────────┐ │ 6 Summary header
│ [ Total ] [ Avg / Period ] [ Peak Period ] [ Transactions ]          │ 7 Stat tiles
│ ┌─ Daily Spend (heatmap, GitHub-style) ───────────────────────────┐ │ 8 Heatmap
│ ┌─ Period Comparison ─────────────┐ ┌─ Breakdown (donut) ─────────┐ │ 9 Two-up row
│ ┌─ Spend by Category  (Grafana-style panel) ──────────────────────┐ │
│ │ toolbar: View · Type · Stack · Scale · TopN · ☰Categories ·      │ │
│ │          ∿Overlays · Budget · SMA · PNG · CSV · Reset · ⟲ · ⛶    │ │ 10 Category panel
│ │ [Total][Avg/Period][Peak Period][Categories]                     │ │
│ │ ┌ main chart (area/bar/lines) + tooltip + drill-down ─────────┐ │ │
│ │ ┌ time-range brush (mini overview) ───────────────────────────┐ │ │
│ │ ┌ legend table (swatch · name% · total · min · max · avg · last)┐│ │
│ └───────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

## B.2 Component inventory

### B.2.1 Shell (top bar, status bar, title)
Identical to the Dashboard's top bar, account button, theme toggle and data status bar (see §2, §4.2). Title: **"Expense Charts"**. The hidden-category lock also exists here (same invisible 15-tap trigger and *"Verification required"* modal); locked categories are masked from every chart, legend, tooltip, donut and CSV export.

### B.2.2 Filters card
| Control | Options |
|---|---|
| **Period** | All Time · Yearly · **Monthly (default)** · Weekly · Daily · Custom Range (+ the matching date input; Custom shows **Start**/**End** and the presets Last 7 days / 30 days / 3 months / 6 months / Year to date) |
| **Breakdown** | None · Category · Source — drives the **donut** card |
| **Bucket by** | Auto · Day · Week · Month · Year — the chart's time granularity, **independent of the period** (tooltip: *"e.g. a Yearly period bucketed by Week"*) |
| **Filter rules** | The same Notion-style builder as the Dashboard (nested AND/OR groups, live), but **13 fields** (Name, Amount, Date, Category, Source, Mode, Comment, Other partner, Splitwise ID, Processed, Add to Split, From Split, Split Added), **no SQL mode**, and rules are **sent to the server** (`filters` parameter) so the aggregates respect them. Changing a rule auto-reloads after ~350 ms. Category/Source/Mode pickers are populated from all-time data. Rules persist in the browser. |
| **Apply Filters** | primary pill button (disabled while loading) |

### B.2.3 Loading and error
Centered **spinner ring + "Loading expenses…"** (or *"Refreshing…"* after the Refresh button); results are hidden while loading. Errors appear in a red box (server message or *"Network error: …"*). If the category data is empty the whole category panel is hidden.

### B.2.4 Summary header + stat tiles
- **Header card:** gradient **period badge** (`2026-11`, `2026-11-02 – 2026-11-08`, `All Time`…) and **Grand Total** in large gradient text.
- **4 stat tiles** (responsive mini-grid):
  | Tile | Value | Sub-text |
  |---|---|---|
  | **Total** | `₹12,345.00` | — |
  | **Avg / Period** | abbreviated (`₹1.2K`) | `across N periods` (only non-zero periods) |
  | **Peak Period** | abbreviated | the label of the highest period |
  | **Transactions** | entry count | — |
- *Abbreviation rule:* `₹ 1.2K` (thousand), `₹ 1.2L` (lakh), `₹ 1.2Cr` (crore); under 1,000 it's a whole number.

### B.2.5 "Daily Spend" heatmap (GitHub-style)
- Shown **only when the range is 14–1,500 days**; otherwise the card is hidden.
- **Weeks are columns, days are rows** (Mon/Wed/Fri labels at the left, month labels along the top with a small gap between months); square cells 11 px with a 3 px gap.
- **5-step indigo scale** relative to the busiest day: none (`#EBEDF0`) · < 15 % · < 40 % · < 70 % · ≥ 70 % (`#C7D2FE → #818CF8 → #4F46E5 → #3730A3`).
- **Hover tooltip** follows the cursor with the date and amount. Legend row: *Less ▢▢▢▢▢ More*.
- Horizontally scrollable on narrow screens.

### B.2.6 Two-up row
1. **Period Comparison** card. Shows *Previous · {label} ₹X → Current · {label} ₹Y* and a **delta chip** `▲ 12.3 %` (red/up), `▼ 8.0 %` (green/down) or `—`. The previous period is derived from the current one: month → previous month, year → previous year, week → previous 7 days, day → previous day, custom → the same-length window immediately before. States: *Loading…*, *"No previous period to compare."* (All Time), *"Could not load previous period."*
2. **Breakdown donut** card (only when **Breakdown ≠ None**): doughnut chart, title `By Category` / `By Source`, legend at the bottom, hover pops the slice (`hoverOffset: 8`), white slice borders.

### B.2.7 "Spend by Category" panel (the centrepiece)
A Grafana-style analytical panel. **All of its settings persist** (browser storage) **and are encoded into the page URL (`?cat=…`) so a view can be shared/bookmarked.**

**Toolbar (segmented toggles `tg`, popovers and inputs)**

| Control | Options | Effect |
|---|---|---|
| **View** | By Category · Overall | one series per category, or a single "Overall" series |
| **Chart type** | Area · Bar · Lines | |
| **Stack** | Stacked · Split | stack series or draw them separately. **Dimmed** (looks disabled) when View = Overall, Type = Lines, or Scale = Share % |
| **Scale** | **Sum** · **Cumul.** · **Share %** · **Index** | raw per-period totals · running total · each category's % of that period · indexed to its first non-zero value = 100 |
| **Top N** | All · Top 5 · Top 10 | limit series; optional **"Group the rest as 'Other'"** (checkbox inside the Categories popover). Dimmed when View = Overall |
| **☰ Categories** (popover) | search box, **All** / **None**, checklist with colour swatches | include/exclude categories; empty state *"Every category is filtered out — open ☰ Categories to add some back."* |
| **∿ Overlays** (popover) | **Trend line** · **Average** · **Median** · **EMA** · **Volatility band** · **Anomaly markers** (each with its colour swatch) | analysis lines drawn over the *displayed total*. Notes: EMA & band need the *SMA window* set. Anomaly = periods above *mean + 2σ* (red diamond markers). Band = moving average ± σ. Trend = least-squares line. |
| **₹ Budget/period** (number; dimmed with SMA and Overlays when Scale = Share % or Index) | any amount | draws a **budget threshold line** and **colours the Avg and Peak stat cells**: *over* (> budget), *near* (> 80 %), *under* |
| **SMA window** (number 0–60) | periods; 0 = off | trailing simple moving average of the total |
| **⤓ PNG** / **⤓ CSV** | | download the chart image / the per-period × category table (`spend-by-category_{period}.png/.csv`) |
| **⟳ Reset** | | reset zoom / brush |
| **⟲** | | rotate fullscreen chart (landscape ⇄ portrait) |
| **⛶** | | fullscreen (button becomes ✕; **Esc** exits) |

**Panel stats row (4 cells):** **Total** · **Avg / Period** (`across N periods`) · **Peak Period** (label) · **Categories** (`top: {name}`).

**Main chart interactions**
- **Hover:** vertical **crosshair** line + a custom **tooltip card** that lists every category for that period **sorted high → low** with colour swatches, in **up to 3 columns** when there are many (≈ 15 rows per column), then a **Total (n)** row, then one row per active overlay. The card flips to the opposite side of the cursor.
- **Click a period:** opens a small **drill-down card** (header = the period label with a ✕; rows of swatch · category · amount sorted high → low; a **Total (n)** footer) anchored to that point; click elsewhere to close.
- **Zoom/pan:** **⌘/Ctrl + scroll** or **pinch** to zoom, **drag to pan**, **double-click to reset**. A hint line under the chart says so.
- **Stable colours:** each category's colour is derived from a hash of its name, so a category keeps its colour across periods, charts, legend and tooltip.

**Time-range brush:** a slim overview area chart under the main chart; **drag across it to zoom** the main chart to that window; **✕ Reset** clears it.

**Legend table** (under the brush): columns **swatch · Category (+ % of total) · Total · Min · Max · Avg · Last**; every header is **sortable** (▾/▴ indicator; default Total ↓).
- **Hover a row →** that series is highlighted and the rest dim; **click a row →** pin the highlight; **click a swatch →** **solo** that category (click again to un-solo).

**Fullscreen:** the panel moves above the page with a dimmed overlay; on narrow screens (< 768 px) it **auto-rotates to landscape**; the rotate button overrides and the choice is remembered.

### B.2.8 State persistence (what survives a reload)
- Filter rules → browser storage (`ps_charts_filters`).
- Panel settings (view, type, stack, scale, top-N, other, budget, SMA, overlays, hidden categories, solo, legend sort, fullscreen orientation) → browser storage (`exp_cat_v1`) **and** the URL (`?cat=<base64>`).
- Period/breakdown/bucket → the URL query string.
- Theme → `ps_theme`; unlock → `sessionStorage`.

## B.3 States
Loading (spinner) · loaded · error · empty category data (panel hidden) · every category excluded (empty message) · no previous period · heatmap hidden (range too short/long) · donut hidden (no breakdown) · fullscreen · zoomed/brushed · series highlighted/pinned/soloed · budget over/near/under.

## B.4 Data the page consumes
| Request | Gives |
|---|---|
| `GET /expenses/chart/?period=…&group_by=…&bucket=…&filters=…` | `grand_total`, `entry_count`, `trend{labels,values}`, `breakdown{labels,values}`, period meta (year/month/week_start/week_end/date/start/end), `display` |
| `GET /expenses/category-timeseries/?…` | `labels[]`, `by_category[{name, values[], total}]` (one value per bucket) |
| `GET /expenses/heatmap/?…` | `daily{ "YYYY-MM-DD": amount }`, `range_start`, `range_end` |
| `GET /expenses/chart/?<previous period>` | the comparison period |
| `GET /expenses/options/` | the person's saved category / source / mode names for the filter pickers |

## B.5 Pain points & opportunities (Charts)
1. **The panel's toolbar is a wall of ~15 controls** with equal weight (View, Type, Stack, Scale, Top N, Categories, Overlays, Budget, SMA, PNG, CSV, Reset, rotate, fullscreen). Group into *Display* (type/stack/scale), *Data* (view/top-N/categories), *Analyse* (overlays/SMA/budget) and *Export/Window* (PNG/CSV/fullscreen) with progressive disclosure; on mobile use a bottom sheet.
2. **Jargon with no explanation:** *Index, Cumul., Share %, EMA, σ band, SMA window, Anomaly*. Add tooltips/inline help and sensible presets ("Trend", "Compare to average").
3. **Page is long and not task-oriented.** Offer a top-level choice of questions ("Am I over budget?", "Where does it go?", "What changed vs last period?") or sticky anchors; make the headline answer (total + vs-previous + budget status) one compact hero.
4. **Duplicate stat blocks:** the 4 stat tiles near the top and the 4 stat cells inside the panel show nearly the same numbers.
5. **Heatmap is desktop-centred** (tiny 11 px cells, hover-only tooltips) — needs touch interaction and a larger mobile layout; no way to click a day to see its transactions.
6. **No link from chart to data:** clicking a period shows a mini breakdown but not the underlying transactions (could deep-link to the Dashboard with that period/category pre-filtered).
7. **State is invisible:** many persisted settings (budget, SMA, overlays, hidden categories) silently affect the chart — show active-setting chips and a "Reset view".
8. **Colour-only encoding** and hash-derived colours can collide or have low contrast; offer a colour-blind-safe palette and direct labels.
9. **Fullscreen/rotate on mobile** is clever but unusual — consider a dedicated landscape-friendly layout.
10. **Two filter UIs** (this one vs the Dashboard's) behave differently (server-side here; SQL mode only on the Dashboard).

## B.6 Charts — must-keep checklist
- [ ] Auto-load on open; Apply Filters; Refresh; status bar; loading/error states
- [ ] Period (6 modes) + presets; Breakdown; Bucket by; rule builder (server-side, auto-apply)
- [ ] Summary header + 4 stat tiles (₹ K/L/Cr abbreviations)
- [ ] Heatmap (14–1,500 day range, 5-step scale, tooltip, legend)
- [ ] Period comparison with delta %; donut breakdown
- [ ] Category panel: View · Type · Stack · Scale · Top N (+Other) · Categories include/exclude · Overlays (6) · Budget line + colouring · SMA · PNG · CSV · Reset · Rotate · Fullscreen
- [ ] Tooltip (multi-column, totals, overlays), crosshair, click-drill-down, zoom/pan/pinch/double-click reset, brush
- [ ] Legend table with sorting, hover-highlight, pin, solo
- [ ] Shareable URL + persisted settings; hidden-category lock respected everywhere

---
---

# PART C — Splitwise page (`/expenses/splitwise/`) — owner only

> Source: `expenses/templates/expenses/splitwise.html` (~1,150 lines, vanilla JS, no chart library).
> Purpose: **see who owes whom on Splitwise and pull Splitwise expenses into your own ledger** (one at a time or in bulk, with duplicate protection).
> Not visible to "expenses-only" accounts (the tab and the route are hidden/blocked). A *different* feature — the per-row **"Split on Splitwise"** panel that *pushes* a ledger entry out to Splitwise — lives on the Dashboard (§4.9).

## C.1 Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ [Home|Dashboard|Charts|Splitwise*]                (● avatar)  (☀)    │ 1 Top bar (shared)
│ Splitwise   as Abhinav                              [⟳ Refresh]      │ 2 Head row
│ ⚠ Splitwise is not connected. Set SPLITWISE_… (banner, only if off)  │ 3 Banner
│ ┌ You owe │ You're owed │ Net position ──────────────────────────┐   │ 4 Balance stats
│  ── VIEW A: Directory ─────────────────────────────────────────────  │
│ ┌ Groups & individuals  [Search groups…] ────────────────────────┐   │ 5 Directory
│ │ ▤ All activity — every recent expense                       ›  │   │
│ │ ◔ Individual / non-group — expenses not in any group        ›  │   │
│ │ ◎ Trip to Goa — 5 members · you lent ₹1,100.00              ›  │   │
│ ┌ Who owes what ─────────────────────────────────────────────────┐   │ 6 Balances
│  ── VIEW B: Group detail (replaces A) ─────────────────────────────  │
│ ← All groups & individuals                                           │ 7 Back
│ ┌ {Group}  · 5 members ─────────────────────────────────────────┐   │
│ │ [All][Not imported][Imported][I paid][Someone else paid]…      │   │ 8 Filter chips
│ │ filter-rule builder                                            │   │ 9 Rule builder
│ │ [Search description…] [Sort ▾] [Mode (optional)]               │   │ 10 Controls
│ │ 12 expenses · ₹4,200.00 total · you lent ₹1,100.00             │   │ 11 Summary line
│ │ Group by ▾ → ranked bars                                        │   │ 12 Group-by
│ │ (bulk bar: N selected · Import selected · Select all · Clear)   │   │ 13 Bulk bar
│ │ ☐ Dinner  [Trip] [Food] [You paid]  2026-11-02      ₹600  you lent… [Import]│ 14 Expense list
│ │ [ Load more ]                                                  │   │ 15 Pagination
└──────────────────────────────────────────────────────────────────────┘
```

## C.2 Component inventory

### C.2.1 Head row
Title **Splitwise**, a muted **"as {your name}"** label once connected, and a **Refresh** button (shows `…` while loading). Refresh reloads the overview (and re-opens the current group).

### C.2.2 Not-connected banner
When Splitwise isn't configured: a banner explains *"Splitwise is not connected. Set SPLITWISE_CONSUMER_KEY / SPLITWISE_CONSUMER_SECRET / SPLITWISE_API_KEY."* and the directory shows *"Not connected."*

### C.2.3 Balance stats (3 tiles)
| Tile | Colour logic |
|---|---|
| **You owe** | red when > 0, neutral when 0 |
| **You're owed** | green when > 0, neutral when 0 |
| **Net position** | green positive · red negative · neutral ≈ 0 |
Amounts use the account currency symbol (₹ $ € £) with Indian grouping.

### C.2.4 View A — Directory
- **"Groups & individuals" card:** a **search** box (*"Search groups…"*, live) and a list of rows. Fixed first two rows: **All activity** (*every recent expense*) and **Individual / non-group** (*expenses not in any group*), then **each group** (name, `N members`). Rows are full-width buttons with an icon, name, sub-line, and a **›** chevron. Once you've opened a group, its row also shows a coloured net tag (`you lent ₹…` green / `you owe ₹…` red). Empty: *"No groups match."*
- **"Who owes what" card:** per-friend balances, **most-owed-by-you first**; header line `You owe ₹X · owed to you ₹Y`; each row: name, `you owe them` / `they owe you`, amount (red/green). Empty: *"All settled up."*

### C.2.5 View B — Group detail
Opens when a directory row is clicked (replaces the directory; **← All groups & individuals** returns).

- **Header:** group name + `N members`.
- **Filter chips (9, multi-select toggles):** **All** · **Not imported** · **Imported** · **I paid** · **Someone else paid** · **I owe on this** · **I'm owed on this** · **Uncategorised** · **Settle-ups**. Several can be active at once (an expense must pass **every** active chip), but **contradicting chips switch each other off** (e.g. *I paid* ⇄ *Someone else paid*; *Imported* ⇄ *Not imported*; *Settle-ups* clears all the others).
- **Rule builder:** the same nested AND/OR builder as the other pages, applied **client-side on top of the chips**, persisted in the browser. **Fields (11):** Name · Amount · Date · Category · Group · Paid by · *My net (+lent / −owe)* · *I paid (amount)* · *My owed share* · *Is settle-up* · *Imported*. No SQL mode.
- **Controls row:** **Search description** (debounced; field highlights when active) · **Sort** (Newest first · Oldest first · Cost: high → low · My share: high → low) · **Mode (optional)** text input — *"Applied to the expense for whatever you import next"* (e.g. UPI).
- **Summary line:** `12 expenses · ₹4,200.00 total · you lent ₹1,100.00 · Not imported + I paid` (shows `settled` / `you owe …` as appropriate and names the active chips).
- **Group by:** None · Category · Group · Paid by → the **same ranked-bars list** used on the Dashboard (name, bar, amount, % and count).
- **Bulk bar** (appears once something is ticked): `N selected` · **Import selected** · **Select all shown** · **Clear**. While importing it reads `Importing 3/10…`.
- **Expense list** (pages of **100**; **Load more** button when more exist):
  - Optional *"Select all N importable"* checkbox.
  - **Row:** checkbox (only on importable rows — not settle-ups, not already imported) · **title** (or `—`) · sub-line of **chips** (`settle-up`, the group name when you're not already inside it, the Splitwise category, **"You / {names} paid"** — up to 3 names then `+N`) and the date · an **Import** button (becomes **✓ Imported**, disabled, once imported; absent for settle-ups).
  - **Right side:** the cost (in the expense's own currency) and **your position**: `you lent ₹…` (green), `you owe ₹…` (red) or `not involved` (neutral).
  - Empty: *"Nothing matches these filters."*; loading: *"Loading…"*.
- **What "Import" does:** creates a ledger expense with **Category = "Splitwise"**, **From Split** ticked, **Source = the payer(s)**, **Amount = your share**, the **breakdown in Comment**, and the **Splitwise ID** recorded so the same expense can't be imported twice (duplicates are rejected). Settle-up payments can't be imported. Success toast: `Imported "Dinner" (₹300.00)`. **Bulk import** runs one at a time, then toasts `N imported, M failed` and lists failures in a browser alert.

### C.2.6 Feedback
Simple toasts at the bottom (success/error, auto-dismiss ~3.5 s) and inline button states (`Import` → `Importing…` → `✓ Imported`).

## C.3 States
Loading · connected · **not connected** · directory empty-search · group loading · list empty (filters exclude everything) · has-more / all-loaded · imported (disabled) · importing · import failed (toast, or alert for bulk) · duplicate-protection unavailable (small hint above the list) · some rows selected (bulk bar).

## C.4 Data the page consumes
| Request | Gives |
|---|---|
| `GET /expenses/splitwise/overview/` | `configured`, `me{id,name,currency}`, `groups[{id,name,members[]}]`, `friends[{id,name,net}]`, `totals{you_owe,you_are_owed,net}` |
| `GET /expenses/splitwise/expenses/?limit=100&offset=…&group_id=…` | `expenses[]` (`id, description, cost, currency, date, category, is_payment, group_id, group_name, users[{id,name,paid,owed}], my_paid_share, my_owed_share, my_net`), `has_more`, `dedupe_enabled`, `already_imported[]` |
| `POST /expenses/splitwise/import/` `{expense_id, mode}` | created expense `{page_id, name, amount, date}` |

## C.5 Pain points & opportunities (Splitwise)
1. **Two disconnected Splitwise surfaces:** this tab *pulls* Splitwise → ledger, while the Dashboard row panel *pushes* ledger → Splitwise. Users can't tell which is which; unify into one "Splitwise" area with *Import* and *Send* clearly separated (and a shared queue).
2. **Directory is a plain list.** No avatars, no sorting by balance, no "settle up" action, no per-person view. A person-first layout ("Who owes what" as the hero) would match how people think.
3. **Net per group is unknown until you open it** (computed from loaded expenses), so the directory shows inconsistent tags.
4. **Filter overload:** 9 chips **plus** a rule builder **plus** search **plus** sort **plus** group-by — and chips/rules overlap in meaning (e.g. *I paid*). Collapse into one filter popover with active-filter chips.
5. **Import affordances are easy to miss:** the *Mode* field sits among filters yet silently affects the next import; bulk bar appears only after ticking; failures use a blocking browser `alert`.
6. **No preview of what will be created** before importing (category, source, amount = your share) and **no undo**.
7. **Multi-currency:** totals mix currencies visually; the stat tiles assume the account currency.
8. **Pagination** is a "Load more" button over client-side filtering — filters only see what's loaded, which is not obvious.
9. **Settled/neutral states** are low-contrast grey; positives/negatives rely on colour alone.

## C.6 Splitwise — must-keep checklist
- [ ] Overview: connected state, "as {name}", Refresh, not-connected banner
- [ ] 3 balance tiles with colour logic; "Who owes what" friend balances
- [ ] Directory: search, All activity, Individual/non-group, each group, net tags
- [ ] Group detail: back, 9 exclusive/combinable chips, rule builder (11 fields, persisted), search, sort (4), Mode input, summary line, group-by (Category/Group/Paid by), Load more (100/page)
- [ ] Row: checkbox, title, chips (settle-up/group/category/payers), date, cost, my position, Import button states
- [ ] Single import and bulk import (select, select-all-shown, clear, progress, results), dedupe via Splitwise ID, settle-ups not importable

---
---

# PART D — Shared components & design-system inventory (all three pages)

The three pages were built separately and **re-implement the same ideas** with small differences. A redesign should define each once.

| Component | Where it appears | Notes / variants today |
|---|---|---|
| **Top bar** (tab nav pill, mobile "Menu" dropdown, account button, theme toggle) | all pages | The nav pill and account/theme buttons are identical everywhere; the account button is a shared partial. |
| **Account menu** | all expenses pages | avatar → name/email, Profile, Sign out |
| **Page background** | all pages (also Login/Profile/Home) | lavender `#F5F4FA` + two floating blurred gradient orbs |
| **Card** (glass) | all | `rgba(255,255,255,.75)`, blur 16 px, radius 20–22 px, hover lift |
| **Primary / ghost / icon buttons** | all | gradient pill; outlined ghost; round icon buttons (Dashboard's expand into labelled pills on hover) |
| **Period controls** (Period + date input + presets) | Dashboard, Charts | same options; different ids and extra "Bucket by"/"Breakdown" on Charts |
| **Filter rule builder** (nested AND/OR) | Dashboard (15 fields + SQL mode, client-side), Charts (13 fields, **server-side**), Splitwise (11 fields, client-side) | **Three copies** of the same UI/logic; operators by type: text / number / date / select / multi / bool |
| **Ranked list** (name · bar · amount · % · count) | Dashboard summary, Splitwise group-by | same markup/behaviour |
| **Stat tiles** | Dashboard (single "Total" row), Charts (mini grid + panel cells), Splitwise (3-up grid) | three different styles for the same idea |
| **Data status bar** ("N loaded · fetched …" + Refresh) | Dashboard, Charts | shown after first load |
| **Load-status chips** | Dashboard only | Recent / All expenses / Splitwise |
| **Toasts** | all | success / error / info on Dashboard; simpler on Charts and Splitwise — three implementations |
| **Modals** | Dashboard (6), Charts (1 unlock) | centered card on backdrop; no shared component |
| **Chips / tags / badges** | all | category tag (indigo), source/mode tag (grey), split badge (pending/queued/done), period badge (gradient pill), count badge, "unlocked" badge |
| **Segmented toggle** | Dashboard (Visual/SQL), Charts toolbar (`tg` groups) | pill group with one active |
| **Popover / dropdown panel** | Charts (Categories, Overlays), account menu, Source/Mode combobox | each custom |
| **Searchable combobox** | Dashboard (Source, Mode, category in split modal) | scrollable list filtered as you type; can add a new value |
| **Skeleton / spinner / empty / error** | all | skeleton rows (Dashboard), spinner ring (Charts), text only (Splitwise) |
| **Tables** | Charts legend | sortable headers |
| **Charts** | Charts page (Chart.js area/bar/line/doughnut + custom heatmap + brush) | stable hash-based per-category colours |
| **Semantic colour use** | all | indigo = primary; green = positive/owed/success; red = negative/owe/danger; amber = overlays/warnings |

**Recommendation for the redesign:** deliver one small design system — tokens (colour, type, radius, shadow, motion), plus components (TopBar, AccountMenu, Card, Button, IconButton, Chip, Badge, SegmentedControl, Popover, Combobox, Modal/BottomSheet, Toast, StatTile, RankList, FilterBuilder, PeriodPicker, DataTable, Skeleton/Empty/Error) — and apply it to **Dashboard, Charts, Splitwise, Login, Profile and Home** together.

---

*Source of truth:* `expenses/templates/expenses/dashboard.html`, `charts.html`, `splitwise.html` (UI + client logic), `expenses/views/expense.py` (HTTP), `expenses/services/expense.py` (rules & calculations), `expenses/data_services/expense.py` (storage). This brief should be regenerated if those change materially.
