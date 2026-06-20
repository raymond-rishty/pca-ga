/* ga53/notes.js — local, per-overture notes for the GA53 layer.
 *
 * Storage: one localStorage key, keyed by OVERTURE NUMBER (stable across amendments / mootness),
 * so re-deploying an amended page never disturbs notes. Shared by the app (/ga53/app/) and the
 * individual overture pages (/ga53/O*.html) — same origin => same store, so a note written on a
 * page shows up in the app and vice-versa.
 *
 * Durability: survives refresh / restart. NOT synced across devices; eroded only by clearing site
 * data, private mode, or (iOS Safari) ~7 days idle for a non-installed site — hence storage.persist()
 * and the export/import file. See SPEC-GA53-NOTES.md.
 */
(function () {
  var KEY = "pca-ga53:notes:v1";
  var ASKED = "pca-ga53:persist-asked";
  var subs = [];
  var store = read();

  function read() { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } }
  function write() { try { localStorage.setItem(KEY, JSON.stringify(store)); return true; } catch (e) { return false; } }
  function emit() { for (var i = 0; i < subs.length; i++) try { subs[i](store); } catch (e) {} }
  function hasContent(n) { return !!(n && (n.text || n.star || n.lean)); }

  var api = {
    available: function () { try { localStorage.setItem("__t", "1"); localStorage.removeItem("__t"); return true; } catch (e) { return false; } },
    get: function (num) { return store[num] || null; },
    all: function () { return store; },
    count: function () { var c = 0; for (var k in store) if (hasContent(store[k])) c++; return c; },
    has: function (num) { return hasContent(store[num]); },
    /* patch = {text?, star?, lean?, seen?}; empty note is deleted */
    set: function (num, patch) {
      var cur = store[num] || {};
      var next = {};
      for (var k in cur) next[k] = cur[k];
      for (var k2 in patch) next[k2] = patch[k2];
      next.ts = Date.now();
      if (!hasContent(next)) { delete store[num]; } else { store[num] = next; }
      write(); emit();
      return store[num] || null;
    },
    onChange: function (cb) { subs.push(cb); },
    exportBlob: function () {
      return new Blob([JSON.stringify({ app: "ga53-notes", v: 1, exported: new Date().toISOString(), notes: store }, null, 2)],
        { type: "application/json" });
    },
    /* merge by default (keep newer ts); mode==='replace' overwrites */
    import: function (obj, mode) {
      var incoming = (obj && obj.notes) ? obj.notes : (obj || {});
      for (var k in incoming) {
        if (mode === "replace" || !store[k] || (incoming[k].ts || 0) > (store[k].ts || 0)) store[k] = incoming[k];
      }
      write(); emit();
    }
  };

  // cross-tab sync
  window.addEventListener("storage", function (e) { if (e.key === KEY) { store = read(); emit(); } });

  // ask once for durable (non-evictable) storage on an installed PWA
  if (navigator.storage && navigator.storage.persist && !localStorage.getItem(ASKED)) {
    try { navigator.storage.persist().catch(function(){}).then(function(){ try{localStorage.setItem(ASKED,"1");}catch(e){} }); } catch (e) {}
  }

  // ---- one-time injected styles (so the panel looks consistent on pages and in the app) ----
  function injectCss() {
    if (document.getElementById("ga53n-css")) return;
    var s = document.createElement("style"); s.id = "ga53n-css";
    s.textContent =
      ".ga53n{border:1px solid #d0d7de;border-radius:12px;background:#fff;padding:12px 14px;margin:0 0 14px;font-size:.92rem}" +
      ".ga53n h2{font-size:.82rem;letter-spacing:.03em;text-transform:uppercase;color:#0f5132;margin:0 0 8px}" +
      ".ga53n .row{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}" +
      ".ga53n button.tog{font-size:.8rem;padding:5px 10px;border:1px solid #d0d7de;border-radius:999px;background:#f6f8fa;color:#1f2328;cursor:pointer}" +
      ".ga53n button.tog[aria-pressed=true]{background:#1a7f37;border-color:#1a7f37;color:#fff;font-weight:600}" +
      ".ga53n textarea{width:100%;min-height:74px;border:1px solid #d0d7de;border-radius:8px;padding:8px 10px;font:inherit;resize:vertical}" +
      ".ga53n .save{color:#636c76;font-size:.76rem;margin-top:6px;min-height:1em}" +
      ".ga53n .stale{background:#fff8c5;color:#9a6700;border:1px solid #eac54f;border-radius:8px;padding:6px 10px;font-size:.8rem;font-weight:600;margin-bottom:8px}";
    document.head.appendChild(s);
  }

  function meta(name) { var m = document.querySelector('meta[name="' + name + '"]'); return m ? m.getAttribute("content") : ""; }
  function overtureFromUrl() { var m = location.pathname.match(/\/(O\d{1,2})\.html?$/i); return m ? m[1].toUpperCase() : (meta("ga53-overture") || ""); }

  /* Mount the note panel for the current overture page into `el`. */
  api.mountPage = function (el) {
    if (!el) return;
    injectCss();
    var num = overtureFromUrl();
    if (!num) { el.style.display = "none"; return; }
    var updated = meta("ga53-updated") || "";
    if (!api.available()) {
      el.className = "ga53n";
      el.innerHTML = '<div class="save">Notes can’t be saved in this browser (private mode or storage disabled).</div>';
      return;
    }
    el.className = "ga53n";
    el.innerHTML =
      '<div class="stale" hidden></div>' +
      '<h2>📝 My note · ' + num + '</h2>' +
      '<div class="row">' +
      '<button class="tog" data-k="star">★ Watch</button>' +
      '<button class="tog" data-k="lean" data-v="for">👍 For</button>' +
      '<button class="tog" data-k="lean" data-v="against">👎 Against</button>' +
      '<button class="tog" data-k="lean" data-v="undecided">🤔 Unsure</button>' +
      '</div>' +
      '<textarea placeholder="Private note (stays on this device) — amendments, questions, how to vote…"></textarea>' +
      '<div class="save"></div>';
    var ta = el.querySelector("textarea");
    var save = el.querySelector(".save");
    var stale = el.querySelector(".stale");

    function refresh() {
      var n = api.get(num) || {};
      ta.value = n.text || "";
      el.querySelector('[data-k="star"]').setAttribute("aria-pressed", n.star ? "true" : "false");
      var btns = el.querySelectorAll('[data-k="lean"]');
      for (var i = 0; i < btns.length; i++) btns[i].setAttribute("aria-pressed", (n.lean === btns[i].getAttribute("data-v")) ? "true" : "false");
      // staleness: page amended after the note was last touched
      if (updated && n.seen && updated > n.seen) {
        stale.hidden = false;
        stale.textContent = "⚠ This overture was updated on " + updated + ", after your note (" + n.seen + ") — re-check it.";
      } else { stale.hidden = true; }
    }
    function touched(extra) {
      var patch = extra || {};
      patch.text = ta.value;
      if (updated) patch.seen = updated;
      api.set(num, patch);
      save.textContent = "Saved ✓";
      setTimeout(function () { save.textContent = ""; }, 1500);
      refresh();
    }
    el.querySelector('[data-k="star"]').addEventListener("click", function () {
      touched({ star: !((api.get(num) || {}).star) });
    });
    var leanBtns = el.querySelectorAll('[data-k="lean"]');
    for (var j = 0; j < leanBtns.length; j++) leanBtns[j].addEventListener("click", function (e) {
      var v = e.currentTarget.getAttribute("data-v");
      var cur = (api.get(num) || {}).lean;
      touched({ lean: cur === v ? null : v });
    });
    var t;
    ta.addEventListener("input", function () { clearTimeout(t); t = setTimeout(function () { touched(); }, 400); });
    api.onChange(refresh);
    refresh();
  };

  window.GA53Notes = api;
})();
