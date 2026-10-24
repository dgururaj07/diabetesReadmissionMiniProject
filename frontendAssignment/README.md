# Frontend: Diabetes Patient Management UI

A plain HTML, CSS and JavaScript page for the care team: no framework, no build step, nothing to install.
It talks to the FastAPI backend at `http://127.0.0.1:8000`.

## Running it

1. **Start the backend** (see [../backend/README.md](../backend/README.md)).
2. **Serve this folder on port 5173**, from the repo root:
   ```powershell
   .venv\Scripts\python.exe -m http.server 5173 --bind 127.0.0.1 --directory frontendAssignment
   ```
3. **Open http://127.0.0.1:5173/index.html.**

**Why not double-click `index.html`?** A page opened from disk (`file:///…`) has origin `null`, so the browser
blocks the API's responses with a CORS error. The backend only allows `http://localhost:5173` and
`http://127.0.0.1:5173`, which is why the port must be 5173.

## The three tabs

The address ends in `#add`, `#search` or `#care`, so a reload stays on the same tab. The left and right arrow keys
move between tabs.

### 1. Add Encounter: `POST /encounters`
- **Form:** all encounter fields. Only Patient Number is required, and it is checked as you type. Number fields
  left empty aren't sent, so the backend's defaults apply.
- **After saving:** the page also fetches `GET /encounters/{id}`, so the new row in **Added Encounters** shows the
  server-calculated risk score, level and review reason, plus intervention status, assigned to and notes.
- **The table** lists only encounters added in this browser session, newest first.

### 2. Search Patients: `GET /patients/search`
- **Filters:** Patient Number, Risk Level and Exact Risk Score (0–8), combined with AND. The **Quick Filter**
  chips set the risk level and search immediately.
- **Results:** HIGH first, then by score. Paging is 50 rows per page with Previous / Next.
- **Buttons:** **Reset Filters** clears the filters and shows everything. **Refresh** reloads the current page of
  results.
- **Shortcut:** clicking an **Encounter ID** opens it in the Care Intervention tab.

### 3. Care Intervention: `GET /encounters/{id}`, then `PATCH /interventions/{id}`
- **Look up:** enter an Encounter ID and click **Fetch Encounter Status** to see its summary: risk, status,
  assigned clinician, notes and last update.
- **Update:** change the status, assigned clinician (100 characters max) or notes, then click **Save
  Intervention**.
- **LOW-risk encounters** have no intervention, so the update form is hidden for them.
- **Fields can't be cleared:** leaving Assigned To or Notes empty keeps the saved value, because the API has no
  way to clear a field.

## Files

| File | Purpose |
|---|---|
| `index.html` | Page structure: tabs, forms, tables |
| `style.css` | Green theme, tabs, chips, badges, layout |
| `app.js` | Add Encounter tab, plus the shared helpers `describeError()` and `getEncounter()` |
| `search.js` | Search Patients tab, plus the shared `badge()` helper |
| `care.js` | Care Intervention tab |
| `tabs.js` | Switches tabs; loaded last because it calls into the other scripts |
| `06_create_encounter.ts` | Standalone TypeScript example of the POST call (not used by the page) |

The scripts are plain `<script>` tags that share one global scope, so **load order matters**: `app.js` →
`search.js` → `care.js` → `tabs.js`. Each file prefixes its own variable names (`search…`, `care…`) to avoid
collisions.

## Conventions

- **Safe display:** API data is put on the page with `textContent`, never `innerHTML`, so stored text can't run
  as HTML.
- **Readable errors:** 400 and 503 messages, and 422 field errors, are shown as text. A failed `fetch` (backend
  down or CORS blocked) shows a hint about the backend and the port.
- **No double submits:** buttons are disabled while their request runs, and a slower, older search can't
  overwrite a newer one.
- **Cache busting:** `index.html` loads its CSS and JS with a `?v=N` suffix. **Increase N whenever you edit
  those files**, or browsers may keep using their saved old copy.
- **API addresses:** `API_URL` (`app.js`), `SEARCH_URL` (`search.js`) and `INTERVENTIONS_URL` (`care.js`).
  Change these if the backend runs elsewhere.
