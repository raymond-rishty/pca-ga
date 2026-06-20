# GA53 Local Notes — Specification

Per-overture **private annotations** for the GA53 (2026) layer: a commissioner reviewing the 90
overtures can jot a note, mark a vote-lean, and star ones to watch — on their phone, offline, with no
account and no server. *(Status: MVP BUILT — `ga53/notes.js`, wired into the overture-page layout and
the GA53 app.)*

This is a **client-side, device-local** feature. The corpus stays a static site (GitHub Pages); notes
never leave the device unless the user exports them. It is deliberately scoped to the GA53 **proposals**
layer and does not touch the adopted-record corpus (see [[proposals-vs-adopted-record]] /
`SPEC-OVERTURES.md`).

## 1. The model

> A note is **one annotation attached to one overture, keyed by its overture number** (`O37`) — free
> text plus light structured flags — stored locally and shown wherever that overture appears (the app
> card and the overture page).

Fields per overture: `{ text, star (watch), lean ('for'|'against'|'undecided'|null), seen (the page
"updated" date when last edited), ts (epoch ms) }`. An all-empty note is deleted. Keyed by **overture
number** because that identity is **stable across amendments and mootness** — the heart of update-safety
(§4).

## 2. Storage & durability

- **Live store:** one `localStorage` key `pca-ga53:notes:v1` → `{ "O37": {…}, … }`. Namespaced because
  *all* of `raymond-rishty.github.io` shares one origin; the `pca-ga53:` prefix avoids collision with the
  corpus app or other sites on that account.
- **Survives** page refresh, tab close, browser restart, device reboot — indefinitely.
- **Eroded only by:** the user clearing site data; private/incognito mode; **iOS Safari ITP** (~7 days
  idle for a *non-installed* site); a different device/browser (no sync). Mitigations:
  - `navigator.storage.persist()` requested once (asks the browser not to evict).
  - Installing the PWA (Add to Home Screen) exempts iOS ITP eviction.
  - **Export / Import** a `ga53-notes.json` file — the durable, user-owned, transferable backup (the
    project's portability ethos applied to notes).
- **Not** cached by a service worker (it's `localStorage`, independent of the SW caches) — so an updated
  page shell never disturbs notes.

## 3. Where it appears (same origin ⇒ one shared store)

- **Overture page** (`/ga53/O*.html`, via the `ga53-overture` layout): a "📝 My note" panel — star /
  for / against / unsure toggles + a textarea (debounced autosave, "Saved ✓"), plus the staleness
  banner (§4).
- **App** (`/ga53/app/`): a note **badge** (★/👍/👎/🤔/📝) on annotated cards; a **"★ My notes (N)"**
  option in the theme dropdown; **Export / Import** buttons. Badges update live via the store's change
  event (and across tabs via the `storage` event).

## 4. Update-safety & staleness (the maintainer's editing workflow)

Re-rendering and re-pushing an amended overture page **never disturbs notes** — they live in
`localStorage` keyed by number, not in the page HTML. Two *staleness* concerns are handled (neither is
data loss):

1. **Context drift** — the overture was amended after the note was written. Each page carries an
   `updated` date (front matter → `<meta name="ga53-updated">`); the note records the date it was last
   edited against (`seen`); if `updated > seen`, the panel shows a non-destructive banner
   *"⚠ This overture was updated on <date>, after your note — re-check it."* Notes are **never**
   auto-deleted on content change.
   - To mark an overture amended: set its date in **`ga53/updated.json`** (`{"O37":"2026-05-12"}`) and
     re-render; default for all others is `DEFAULT_UPDATED` in `36_ga53_overtures.py`.
2. **Stale cache** — the page service worker is cache-first, so a user could keep seeing the old HTML.
   **Bump the SW cache versions on a content deploy** (`pca-ga53-pages-v*` for pages, `pca-ga53-v*` for
   the app) so amendments reach users; the app reloads once on `controllerchange`.

**Lifecycle rule:** when an overture goes moot/withdrawn, **mark it in place — never delete the page**,
or the note's link target 404s (the note itself still survives). Moot overtures stay on the docket
anyway.

## 5. Build / integration

- `ga53/notes.js` — the shared module (store API + page panel UI + injected styles). One file, loaded by
  the layout (`notes.js`) and the app (`../notes.js`); same origin ⇒ same store.
- `36_ga53_overtures.py` (`render_app`) copies `notes.js` into `<ROOT>/ga53/` and stamps each page's
  `updated` front matter; runs for both trees via `render.sh`.
- Caching: the page SW (`/ga53/`) caches `notes.js` and the pages; the app SW (`/ga53/app/`) caches the
  shared `notes.js` too (it lives outside `/app/`), so both surfaces work offline.

## 6. Invariants (acceptance)

1. A note survives refresh, restart, and a re-deploy of its overture page.
2. Notes are keyed by overture number; amending/mooting a page keeps the note attached.
3. Content updates never delete a note; staleness is surfaced, not destructive.
4. The feature degrades gracefully where storage is unavailable (a one-line notice, no crash).
5. Notes are device-local and private; the only way off-device is an explicit export.
6. GA53 notes touch nothing in the adopted-record corpus.

## 7. Honest limitations

- **No cross-device sync** — by design (no backend). Export/import is the bridge; a future opt-in sync
  (Gist/Drive/serverless KV) is possible but out of scope and adds privacy surface.
- **Per-browser** — notes in phone Safari ≠ laptop Chrome.
- **iOS ITP / clearing data** can still erase the live store; the export file is the backstop.
- `updated` dates are **maintainer-supplied** (`ga53/updated.json`), not auto-detected — accurate but
  manual.
