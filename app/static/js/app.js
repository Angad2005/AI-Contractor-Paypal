/*
 * Shared personalization + accessibility preferences.
 * Load this in <head> (not deferred) on every page so saved settings are applied
 * before first paint. Settings persist in localStorage and sync across tabs.
 */
(function () {
  "use strict";

  var KEY = "aicp:prefs:v1";
  var DEFAULTS = {
    theme: "system", accent: "lime", scale: 100, font: "default",
    spacing: "normal", motion: "system", focus: "standard",
    links: false, calm: false, targets: false
  };
  var ENUMS = {
    theme: ["system", "dark", "light", "contrast"],
    accent: ["lime", "aqua", "violet", "amber", "rose"],
    font: ["default", "readable", "system"],
    spacing: ["normal", "relaxed"],
    motion: ["system", "reduce", "full"],
    focus: ["standard", "strong"]
  };
  var THEME_COLOR = { dark: "#050c09", light: "#f3f6f0", contrast: "#000000" };
  var SWATCHES = {
    lime: ["Lime", "199,243,107"], aqua: ["Aqua", "94,234,212"], violet: ["Violet", "178,156,255"],
    amber: ["Amber", "255,194,77"], rose: ["Rose", "255,140,170"]
  };

  var root = document.documentElement;

  function mq(q) {
    try { return window.matchMedia(q); } catch (e) { return { matches: false }; }
  }
  var mqLight = mq("(prefers-color-scheme: light)");
  var mqReduce = mq("(prefers-reduced-motion: reduce)");

  function clean(raw) {
    var p = {}, k;
    raw = raw && typeof raw === "object" ? raw : {};
    for (k in DEFAULTS) p[k] = DEFAULTS[k];
    for (k in ENUMS) if (ENUMS[k].indexOf(raw[k]) !== -1) p[k] = raw[k];
    var s = Number(raw.scale);
    if (isFinite(s)) p.scale = Math.min(150, Math.max(85, Math.round(s / 5) * 5));
    ["links", "calm", "targets"].forEach(function (b) { if (typeof raw[b] === "boolean") p[b] = raw[b]; });
    return p;
  }

  function load() {
    try { return clean(JSON.parse(localStorage.getItem(KEY) || "{}")); }
    catch (e) { return clean({}); }
  }
  function save(p) {
    try { localStorage.setItem(KEY, JSON.stringify(p)); } catch (e) { /* storage blocked: settings last for this page only */ }
  }

  var prefs = load();

  function resolvedTheme(p) { return p.theme === "system" ? (mqLight.matches ? "light" : "dark") : p.theme; }
  function resolvedMotion(p) { return p.motion === "system" ? (mqReduce.matches ? "reduce" : "full") : p.motion; }

  function apply(p) {
    var theme = resolvedTheme(p);
    root.setAttribute("data-theme", theme);
    root.setAttribute("data-accent", p.accent);
    root.setAttribute("data-font", p.font);
    root.setAttribute("data-spacing", p.spacing);
    root.setAttribute("data-motion", resolvedMotion(p));
    root.setAttribute("data-focus", p.focus);
    root.setAttribute("data-links", p.links ? "on" : "off");
    root.setAttribute("data-calm", p.calm ? "on" : "off");
    root.setAttribute("data-targets", p.targets ? "on" : "off");
    root.style.setProperty("--text-scale", String(p.scale / 100));
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", THEME_COLOR[theme] || THEME_COLOR.dark);
  }

  apply(prefs);

  function onSystemChange() { if (prefs.theme === "system" || prefs.motion === "system") apply(prefs); }
  [mqLight, mqReduce].forEach(function (m) {
    if (m.addEventListener) m.addEventListener("change", onSystemChange);
    else if (m.addListener) m.addListener(onSystemChange);
  });

  window.Prefs = {
    get: function () { return clean(prefs); },
    reducedMotion: function () { return root.getAttribute("data-motion") === "reduce"; }
  };

  /* ---------------- UI ---------------- */

  function seg(name, legend, opts) {
    return '<fieldset class="pf-group"><legend>' + legend + '</legend><div class="pf-seg">' +
      opts.map(function (o) {
        return '<label><input type="radio" name="pref-' + name + '" value="' + o[0] + '" data-label="' + o[1] + '"><span>' + o[1] + '</span></label>';
      }).join("") + "</div></fieldset>";
  }
  function toggle(name, title, hint) {
    return '<label class="pf-switch"><input type="checkbox" role="switch" name="pref-' + name + '" data-label="' + title + '">' +
      '<span class="pf-track" aria-hidden="true"></span><span class="pf-switch-text"><b>' + title + "</b><small>" + hint + "</small></span></label>";
  }

  var panel, fab, out, live, lastFocus;

  function build() {
    // Skip link + main landmark target
    var main = document.querySelector("main");
    if (main) {
      if (!main.id) main.id = "main";
      main.setAttribute("tabindex", "-1");
      var skip = document.createElement("a");
      skip.className = "skip-link";
      skip.href = "#" + main.id;
      skip.textContent = "Skip to main content";
      document.body.insertBefore(skip, document.body.firstChild);
    }

    live = document.createElement("div");
    live.className = "sr-only";
    live.setAttribute("role", "status");
    live.setAttribute("aria-live", "polite");
    document.body.appendChild(live);

    fab = document.createElement("button");
    fab.type = "button";
    fab.className = "pf-fab";
    fab.setAttribute("aria-label", "Appearance and accessibility settings");
    fab.setAttribute("aria-expanded", "false");
    fab.setAttribute("aria-controls", "prefs-panel");
    fab.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/></svg>';

    var swatches = Object.keys(SWATCHES).map(function (k) {
      return '<label class="pf-swatch" style="--sw:' + SWATCHES[k][1] + '"><input type="radio" name="pref-accent" value="' + k + '" data-label="' + SWATCHES[k][0] + ' accent"><span aria-hidden="true"></span><em class="sr-only">' + SWATCHES[k][0] + "</em></label>";
    }).join("");

    panel = document.createElement("div");
    panel.id = "prefs-panel";
    panel.className = "pf-panel";
    panel.hidden = true;
    panel.tabIndex = -1;
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-labelledby", "pf-title");
    panel.innerHTML =
      '<div class="pf-head"><div><h2 id="pf-title">Personalize</h2><p>Saved on this device and applied to every page.</p></div>' +
      '<button type="button" class="pf-close" aria-label="Close settings">✕</button></div>' +
      seg("theme", "Theme", [["system", "Auto"], ["dark", "Dark"], ["light", "Light"], ["contrast", "High contrast"]]) +
      '<fieldset class="pf-group"><legend>Accent colour</legend><div class="pf-swatches">' + swatches + "</div></fieldset>" +
      '<div class="pf-group"><label class="pf-range-label" for="pref-scale">Text &amp; interface size <output id="pf-scale-out" for="pref-scale"></output></label>' +
      '<input type="range" id="pref-scale" name="pref-scale" min="85" max="150" step="5"></div>' +
      seg("font", "Font", [["default", "Default"], ["readable", "Hyperlegible"], ["system", "System"]]) +
      seg("spacing", "Text spacing", [["normal", "Normal"], ["relaxed", "Relaxed"]]) +
      seg("motion", "Animations", [["system", "Match device"], ["reduce", "Reduced"], ["full", "Full"]]) +
      seg("focus", "Keyboard focus outline", [["standard", "Standard"], ["strong", "Strong"]]) +
      '<div class="pf-group pf-toggles">' +
      toggle("links", "Underline links", "Makes links easier to spot without relying on colour.") +
      toggle("calm", "Calm background", "Hides the animated glow and grid.") +
      toggle("targets", "Large click targets", "Taller buttons and fields for easier tapping.") +
      "</div>" +
      '<button type="button" class="pf-reset">Reset to defaults</button>';

    out = panel.querySelector("#pf-scale-out");
    document.body.appendChild(panel);
    document.body.appendChild(fab);

    fab.addEventListener("click", function () { panel.hidden ? open() : close(true); });
    panel.querySelector(".pf-close").addEventListener("click", function () { close(true); });
    panel.querySelector(".pf-reset").addEventListener("click", function () {
      prefs = clean({});
      commit("Settings reset to defaults");
    });

    panel.addEventListener("change", function (e) {
      var t = e.target;
      if (!t || !t.name || t.name.indexOf("pref-") !== 0) return;
      var key = t.name.slice(5);
      if (t.type === "radio") prefs[key] = t.value;
      else if (t.type === "checkbox") prefs[key] = t.checked;
      prefs = clean(prefs);
      commit(t.getAttribute("data-label") + (t.type === "checkbox" ? (t.checked ? " on" : " off") : " selected"));
    });
    panel.querySelector("#pref-scale").addEventListener("input", function (e) {
      prefs.scale = Number(e.target.value);
      prefs = clean(prefs);
      apply(prefs); save(prefs); sync();
    });

    panel.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.stopPropagation(); close(true); return; }
      if (e.key !== "Tab") return;
      var f = panel.querySelectorAll('button, input:not([type="hidden"])');
      var items = Array.prototype.filter.call(f, function (n) { return !n.disabled; });
      if (!items.length) return;
      var first = items[0], last = items[items.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === panel)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !panel.hidden) close(true); });
    document.addEventListener("click", function (e) {
      if (!panel.hidden && !panel.contains(e.target) && !fab.contains(e.target)) close(false);
    });

    sync();
  }

  function sync() {
    if (!panel) return;
    Array.prototype.forEach.call(panel.querySelectorAll("input"), function (i) {
      var k = i.name.slice(5);
      if (i.type === "radio") i.checked = String(prefs[k]) === i.value;
      else if (i.type === "checkbox") i.checked = !!prefs[k];
      else if (i.type === "range") i.value = prefs[k];
    });
    out.textContent = prefs.scale + "%";
    panel.querySelector("#pref-scale").setAttribute("aria-valuetext", prefs.scale + " percent");
  }

  function commit(message) {
    apply(prefs); save(prefs); sync();
    if (message && live) { live.textContent = ""; setTimeout(function () { live.textContent = message; }, 30); }
  }

  function open() {
    lastFocus = document.activeElement;
    panel.hidden = false;
    fab.setAttribute("aria-expanded", "true");
    panel.focus();
  }
  function close(restore) {
    panel.hidden = true;
    fab.setAttribute("aria-expanded", "false");
    if (restore) fab.focus();
  }

  // Keep every open tab/page in sync
  window.addEventListener("storage", function (e) {
    if (e.key !== KEY) return;
    prefs = load();
    apply(prefs);
    sync();
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build);
  else build();
})();

/* ---------- Shared: cursor spotlight on cards (all pages) ---------- */
document.addEventListener("mousemove", function (event) {
  document.querySelectorAll(".card").forEach(function (card) {
    var rect = card.getBoundingClientRect();
    card.style.setProperty("--mx", (event.clientX - rect.left) + "px");
    card.style.setProperty("--my", (event.clientY - rect.top) + "px");
  });
});

/* ---------- Landing page logic (runs only where the brief form exists) ---------- */
(function () {
  function init() {
    if (!document.getElementById("create")) return;
    const $ = (id) => document.getElementById(id);
    let jobId = null;
    const scrollBehavior = () => (window.Prefs && window.Prefs.reducedMotion() ? "auto" : "smooth");

    const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    }[c]));

    function showError(message) { $("error").textContent = message; }

    function setLoading(button, on) {
      button.classList.toggle("loading", on);
    }

    function renderContract(job) {
      $("contract-price").textContent = `$${job.price.toFixed(2)} ${job.currency}`;
      $("criteria").innerHTML = job.contract.criteria.map((criterion) => `<div class="criterion"><span class="check">✓</span><div><strong>${esc(criterion.label)}</strong><small>${esc(criterion.detail)}</small></div></div>`).join("");
      $("contract").classList.remove("hidden");
      $("contract").scrollIntoView({ behavior: scrollBehavior(), block: "center" });
    }

    $("create").onclick = async () => {
      showError("");
      const button = $("create");
      setLoading(button, true);
      try {
        const response = await fetch("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt: $("prompt").value, budget: Number($("budget").value) }) });
        if (!response.ok) throw new Error("Please add a little more detail to your brief.");
        const job = await response.json(); jobId = job.id; renderContract(job);
      } catch (error) { showError(error.message); }
      finally { setLoading(button, false); }
    };

    $("approve").onclick = async () => {
      const button = $("approve");
      setLoading(button, true);
      const approved = await fetch(`/api/jobs/${jobId}/approve-spec`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approved: true }) });
      setLoading(button, false);
      if (!approved.ok) { showError("The acceptance contract could not be approved."); return; }
      $("contract").classList.add("hidden"); $("progress").classList.remove("hidden");
      $("scan").classList.remove("done");
      $("progress").scrollIntoView({ behavior: scrollBehavior(), block: "center" });
      await fetch(`/api/jobs/${jobId}/run`, { method: "POST" }); poll();
    };

    async function poll() {
      const job = await (await fetch(`/api/jobs/${jobId}`)).json();
      if (["SPEC_APPROVED", "GENERATING", "VERIFYING", "REPAIRING"].includes(job.status)) {
        const labels = {
          SPEC_APPROVED: "Contract locked. Starting the build",
          GENERATING: "Generating your deliverable",
          VERIFYING: "Verifying every acceptance criterion",
          REPAIRING: "Repairing failed checks"
        };
        $("status-title").textContent = labels[job.status] || "Working";
        setTimeout(poll, 500);
        return;
      }
      renderResults(job);
    }

    function renderResults(job) {
      const latest = job.runs.at(-1);
      $("scan").classList.add("done");
      $("status-title").textContent = job.status === "VERIFIED" ? "Verified. Ready for checkout." : "Verification needs attention";
      $("status-copy").textContent = job.status === "VERIFIED" ? "Every acceptance criterion passed independently." : "The contractor could not satisfy every approved check.";
      const ok = job.status === "VERIFIED";
      $("status-dot").style.background = ok ? "var(--lime)" : "var(--red)";
      $("status-dot").style.boxShadow = `0 0 20px ${ok ? "var(--lime)" : "var(--red)"}`;
      $("status-dot").style.animation = "none";

      // Show verification results with evidence
      $("checks").innerHTML = latest ? latest.results.map((result) => `
        <div class="result">
          <div>
            <span>${esc(result.label)}</span>
            ${result.evidence ? `<small class="muted">${esc(result.evidence)}</small>` : ''}
          </div>
          <span class="${result.passed ? "pass" : "fail"}">${result.passed ? "PASS" : "FAIL"}</span>
        </div>
      `).join("") : "";

      // Add preview buttons
      let buttons = "";
      if (job.status === "VERIFIED") {
        buttons += `<button class="primary" id="checkout">Create PayPal Sandbox order <span>→</span></button>`;
      }
      if (latest && latest.results.length > 0) {
        buttons += `<button class="secondary" id="preview-annotated">View Annotated Preview <span>→</span></button>`;
      }
      if (job.runs.length > 1) {
        buttons += `<button class="secondary" id="view-versions">View Version History <span>→</span></button>`;
      }

      $("actions").innerHTML = buttons || `<p class="muted">The payment gate remains closed until every approved criterion passes.</p>`;
      $("progress").scrollIntoView({ behavior: scrollBehavior(), block: "center" });

      if ($("checkout")) $("checkout").onclick = checkout;
      if ($("preview-annotated")) $("preview-annotated").onclick = () => window.open(`/api/jobs/${jobId}/preview/annotated`, '_blank');
      if ($("view-versions")) $("view-versions").onclick = viewVersions;
    }

    async function checkout() {
      const button = $("checkout");
      setLoading(button, true);
      const response = await fetch(`/api/jobs/${jobId}/paypal/order`, { method: "POST" });
      const order = await response.json();
      setLoading(button, false);
      if (!response.ok) { showError(order.detail || "PayPal could not create the order."); return; }
      const approval = order.approve_url ? `<a class="primary" href="${esc(order.approve_url)}" target="_blank" rel="noopener">Open PayPal Sandbox approval <span>↗</span></a>` : `<p class="muted">Mock order mode is active; no external approval is required.</p>`;
      $("actions").innerHTML = `<p class="muted">Order <strong>${esc(order.id)}</strong> created for $${esc(order.amount)} ${esc(order.currency)}. Complete buyer approval, then confirm capture below.</p>${approval}<button class="primary" id="capture">Confirm server-side capture <span>→</span></button>`;
      $("capture").onclick = async () => {
        setLoading($("capture"), true);
        const captured = await fetch(`/api/jobs/${jobId}/paypal/capture`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ order_id: order.id }) });
        const result = await captured.json();
        if (!captured.ok) { setLoading($("capture"), false); showError(result.detail || "PayPal capture was not confirmed."); return; }
        $("actions").innerHTML = `<p class="muted">Payment <strong>${esc(result.capture_id)}</strong> was confirmed by the server.</p><button class="primary" id="download">Download verified source ZIP <span>↓</span></button>`;
        $("download").onclick = () => { window.location = `/api/jobs/${jobId}/download`; };
        confetti();
      };
    }

    async function viewVersions() {
      const response = await fetch(`/api/jobs/${jobId}/versions`);
      const versions = await response.json();
      if (!response.ok) { showError("Could not load version history."); return; }

      const versionHtml = versions.map((v, i) => `
        <div class="version-item" style="animation-delay:${i * 0.07}s">
          <span>Attempt ${esc(v.attempt)}</span>
          <span class="${v.passed ? 'pass' : 'fail'}">${esc(v.pass_count)}/${esc(v.check_count)} checks passed</span>
          ${v.has_browser_results ? '<span class="muted">• Browser tested</span>' : ''}
        </div>
      `).join('');

      $("checks").innerHTML = `<h3>Version History</h3><div class="version-list">${versionHtml}</div>`;
    }

    /* Small celebratory burst after a confirmed payment */
    function confetti() {
      if (window.Prefs && window.Prefs.reducedMotion()) return;
      const cs = getComputedStyle(document.documentElement);
      const colors = [`rgb(${cs.getPropertyValue("--fill-rgb")})`, `rgb(${cs.getPropertyValue("--fill-2-rgb")})`, "#ffffff"];
      const layer = document.createElement("div");
      layer.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:50;overflow:hidden";
      document.body.appendChild(layer);
      for (let i = 0; i < 70; i++) {
        const piece = document.createElement("i");
        const size = 5 + Math.random() * 7;
        piece.style.cssText = `position:absolute;left:${40 + Math.random() * 20}%;top:55%;width:${size}px;height:${size * 1.6}px;background:${colors[i % colors.length]};border-radius:2px;opacity:1`;
        layer.appendChild(piece);
        const dx = (Math.random() - .5) * 900;
        const dy = -250 - Math.random() * 450;
        piece.animate([
          { transform: "translate(0,0) rotate(0)", opacity: 1 },
          { transform: `translate(${dx}px,${dy}px) rotate(${Math.random() * 720}deg)`, opacity: 1, offset: .55 },
          { transform: `translate(${dx * 1.1}px,${dy + 700}px) rotate(${Math.random() * 1080}deg)`, opacity: 0 }
        ], { duration: 1800 + Math.random() * 900, easing: "cubic-bezier(.2,.7,.3,1)" });
      }
      setTimeout(() => layer.remove(), 2900);
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
