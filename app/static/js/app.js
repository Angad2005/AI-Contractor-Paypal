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
    const money = (amount) => {
      try { return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(amount || 0)); }
      catch { return `$${Number(amount || 0).toFixed(2)}`; }
    };

    function renderBill(job, paid) {
      const bill = $("bill");
      const items = Array.isArray(job.bill_items) ? job.bill_items : [];
      if (!items.length) { bill.innerHTML = ""; bill.classList.add("hidden"); return; }
      const labels = { passed: "PASSED · BILLED", failed: "FAILED · $0", skipped: "SKIPPED · $0", pending: "NOT CHECKED" };
      const statusClasses = { passed: "pass", failed: "fail", skipped: "muted", pending: "muted" };
      bill.innerHTML = `
        <div class="invoice-head">
          <div><span class="invoice-kicker">ITEMIZED BILL</span><h3>Acceptance check charges</h3></div>
          <span class="invoice-count">${Number(job.criteria_passed || 0)} / ${Number(job.criteria_total || 0)} billable checks passed</span>
        </div>
        <p class="invoice-note">The approved budget is divided evenly across the acceptance checks. Only passed checks are charged; each failed or skipped check is $0.</p>
        <div class="invoice-columns" aria-hidden="true"><span>ACCEPTANCE CHECK</span><span>RESULT</span><span>SHARE</span><span>CHARGED</span></div>
        <div class="invoice-lines">${items.map((item) => {
          const state = String(item.status || "pending").toLowerCase();
          return `<div class="invoice-line">
            <div class="invoice-description"><strong>${esc(item.label)}</strong>${item.detail ? `<small>${esc(item.detail)}</small>` : ""}</div>
            <span class="invoice-state ${statusClasses[state] || "muted"}">${labels[state] || esc(state.toUpperCase())}</span>
            <span class="invoice-share">${money(item.allocated_amount)}</span>
            <strong class="invoice-charge">${money(item.billed_amount)}</strong>
          </div>`;
        }).join("")}</div>
        <div class="invoice-totals">
          <div><span>Approved budget</span><strong>${money(job.total_budget ?? job.price)}</strong></div>
          <div class="invoice-due"><span>${paid ? "Paid" : "Amount due"}</span><strong>${money(job.payable_amount)}</strong></div>
        </div>`;
      bill.classList.remove("hidden");
    }

    function showError(message) {
      const progressVisible = !$("progress").classList.contains("hidden");
      const target = progressVisible ? $("payment-error") : $("error");
      if (target) target.textContent = message;
    }

    function setLoading(button, on) {
      button.classList.toggle("loading", on);
      button.disabled = on;
    }

    async function loadPaypalDiagnostics() {
      const response = await fetch(`/api/jobs/${jobId}/paypal/diagnostics`);
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || "Could not inspect this PayPal order.");
      return result;
    }

    async function inspectPaypalSeller(button) {
      setLoading(button, true);
      try {
        const diagnostic = await loadPaypalDiagnostics();
        const currency = esc(diagnostic.currency || "unknown currency");
        const amount = esc(diagnostic.amount || "unknown amount");
        const status = esc(diagnostic.status || "unknown");
        const merchant = diagnostic.payee_merchant_id
          ? `PayPal's Sandbox seller merchant ID is ${esc(diagnostic.payee_merchant_id)}. Compare it with the Test Store account where you enabled currency conversion; if they differ, use that Test Store's REST app credentials in the app's Sandbox configuration.`
          : "PayPal did not include a seller merchant ID. Confirm the app uses the Sandbox REST app credentials owned by the Test Store account whose preferences you changed.";
        showError(`PayPal order ${amount} ${currency} (status ${status}). ${merchant} If the IDs match but PayPal reports UNSUPPORTED_PAYEE_CURRENCY, PayPal is rejecting this currency for that seller or region.`);
      } catch (error) {
        showError(error.message || "Could not inspect this PayPal order.");
      } finally {
        if (button.isConnected) setLoading(button, false);
      }
    }

    function renderContract(job) {
      $("contract-price").textContent = `Up to ${money(job.price)}`;
      const criteria = job.contract.criteria || [];
      const totalCents = Math.round(Number(job.price) * 100);
      const baseCents = criteria.length ? Math.floor(totalCents / criteria.length) : 0;
      const remainderCents = criteria.length ? totalCents % criteria.length : 0;
      $("criteria").innerHTML = criteria.map((criterion, index) => {
        const share = (baseCents + (index < remainderCents ? 1 : 0)) / 100;
        return '<div class="criterion"><span class="check">✓</span><div class="criterion-info"><strong>' +
          esc(criterion.label) + '</strong><small>' + esc(criterion.detail) +
          '</small></div><span class="criterion-share">Share ' + money(share) + '</span></div>';
      }).join("");
      $("contract").classList.remove("hidden");
      $("contract").scrollIntoView({ behavior: scrollBehavior(), block: "center" });
    }

    $("create").onclick = async () => {
      showError("");
      const button = $("create");
      setLoading(button, true);
      try {
        const response = await fetch("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt: $("prompt").value, budget: Number($("budget").value) }) });
        const job = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(job.detail || "Please add a little more detail to your brief.");
        jobId = job.id; renderContract(job);
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
      if (["SPEC_APPROVED", "GENERATING", "REBUILDING", "VERIFYING", "REPAIRING"].includes(job.status)) {
        const labels = {
          SPEC_APPROVED: "Contract locked. Starting the build",
          GENERATING: "Generating your deliverable",
          REBUILDING: "Replacing the previous preview with a prompt-specific AI build",
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
      const generationError = latest && latest.results.find((result) => result.key === "generation");
      const acceptanceKeys = new Set((job.contract?.criteria || []).map((criterion) => criterion.key));
      const paid = job.paid || ["PAID", "DELIVERED"].includes(job.status);
      const paymentPending = job.status === "PAYMENT_PENDING";
      const payable = Number(job.payable_amount ?? job.price ?? 0);
      const checkoutReady = Boolean(job.can_checkout ?? ["VERIFIED", "BILLABLE"].includes(job.status)) && payable > 0;
      const allCriteriaPassed = Number(job.criteria_total || 0) > 0 && Number(job.criteria_passed || 0) === Number(job.criteria_total || 0);
      const verified = job.status === "VERIFIED" || (checkoutReady && allCriteriaPassed);
      const billable = job.status === "BILLABLE" || (checkoutReady && !allCriteriaPassed);
      renderBill(job, paid);
      $("scan").classList.add("done");
      $("status-title").textContent = paid ? "Payment confirmed. Delivery is ready." : verified ? "Verified. Continue to payment." : billable ? "Partial results are billable. Continue to payment." : paymentPending ? "PayPal approval is pending." : generationError ? "AI generation could not complete." : "Verification needs attention";
      $("status-copy").textContent = paid ? "The server confirmed payment. Your verified source ZIP is ready." : verified ? `All ${job.criteria_total} acceptance checks passed. Amount due: ${money(payable)}.` : billable ? `${job.criteria_passed} of ${job.criteria_total} acceptance checks passed. Only passed checks are billed: ${money(payable)}.` : paymentPending ? `Approve the ${money(payable)} order with PayPal, then return here to confirm capture.` : generationError ? generationError.evidence : "No approved acceptance checks passed, so there is no payment due.";
      const ok = verified || billable || paid || checkoutReady;
      const dotColor = ok ? "var(--lime)" : paymentPending ? "#f6c453" : "var(--red)";
      $("status-dot").style.background = dotColor;
      $("status-dot").style.boxShadow = `0 0 20px ${dotColor}`;
      $("status-dot").style.animation = "none";

      // Show verification results with evidence
      $("checks").innerHTML = latest ? latest.results.map((result) => `
        <div class="result">
          <div>
            <span>${esc(result.label)}</span>
            <small class="muted">${acceptanceKeys.has(result.key) ? "BUDGET CHECK" : "QUALITY CHECK · NOT BILLED"}</small>
            ${result.evidence ? `<small class="muted">${esc(result.evidence)}</small>` : ''}
          </div>
          <span class="${result.skipped ? "muted" : result.passed ? "pass" : "fail"}">${result.skipped ? "SKIPPED" : result.passed ? "PASS" : "FAIL"}</span>
        </div>
      `).join("") : "";

      let buttons = "";
      if (paid) {
        buttons += `<p class="muted">Capture <strong>${esc(job.capture_id || "confirmed")}</strong> was verified by the server.</p><button class="primary" id="download">Download verified source ZIP <span>↓</span></button>`;
      } else if (checkoutReady) {
        buttons += `<button class="paypal-button" id="checkout"><span class="paypal-wordmark" aria-label="PayPal">PayPal</span><span>Continue to payment · ${money(payable)}</span><span aria-hidden="true">→</span></button>`;
      } else if (paymentPending) {
        buttons += `<p class="muted">Order <strong>${esc(job.payment_order_id || "")}</strong> for ${money(payable)} is waiting for buyer approval.</p>`;
        if (job.payment_approval_url) buttons += `<a class="paypal-button" href="${esc(job.payment_approval_url)}"><span class="paypal-wordmark" aria-label="PayPal">PayPal</span><span>Continue to PayPal checkout</span><span aria-hidden="true">↗</span></a>`;
        else if (String(job.payment_mode).toLowerCase() === "mock") buttons += `<p class="muted mock-payment-note">Mock mode is active. This order will not charge a PayPal account. Set <code>PAYPAL_MODE=sandbox</code> to use PayPal Sandbox.</p>`;
        buttons += `<p class="muted">If PayPal reports that the seller does not accept this currency, enable it or allow conversion in the seller account’s payment receiving preferences, then reset the order.</p>`;
        if (String(job.payment_mode).toLowerCase() !== "mock") buttons += `<button class="secondary" id="paypal-diagnostics">Inspect PayPal seller and currency <span>⌕</span></button>`;
        buttons += `<button class="secondary" id="reset-checkout">Reset this order and retry checkout <span>↻</span></button>`;
        buttons += `<button class="secondary" id="capture">${String(job.payment_mode).toLowerCase() === "mock" ? "Complete mock payment" : "Retry payment confirmation"} <span>→</span></button>`;
      }
      if (job.can_regenerate) {
        buttons += `<button class="secondary" id="rebuild">Regenerate software with AI <span>↻</span></button>`;
      }
      if (job.preview_ready && latest && latest.results.length > 0) {
        buttons += `<button class="secondary" id="preview-annotated">View Read-only Annotated Preview <span>→</span></button>`;
      }
      $("actions").innerHTML = buttons || `<p class="muted">The payment gate opens when at least one approved acceptance check passes.</p>`;
      $("progress").scrollIntoView({ behavior: scrollBehavior(), block: "center" });

      if ($("checkout")) $("checkout").onclick = checkout;
      if ($("rebuild")) $("rebuild").onclick = () => regenerate($("rebuild"));
      if ($("capture")) $("capture").onclick = () => capturePayment(job.payment_order_id, $("capture"));
      if ($("paypal-diagnostics")) $("paypal-diagnostics").onclick = () => inspectPaypalSeller($("paypal-diagnostics"));
      if ($("reset-checkout")) $("reset-checkout").onclick = () => resetCheckout($("reset-checkout"));
      if ($("download")) $("download").onclick = () => { window.location = `/api/jobs/${jobId}/download`; };
      if ($("preview-annotated")) $("preview-annotated").onclick = () => window.open(`/api/jobs/${jobId}/preview/annotated`, '_blank');
    }

    async function regenerate(button) {
      setLoading(button, true);
      const response = await fetch(`/api/jobs/${jobId}/run`, { method: "POST" });
      const result = await response.json().catch(() => ({}));
      setLoading(button, false);
      if (!response.ok) { showError(result.detail || "The software could not be queued for regeneration."); return; }
      showError("");
      $("scan").classList.remove("done");
      $("status-title").textContent = "Regenerating your software with AI";
      $("status-copy").textContent = "The approved contract stays in place while the product is rebuilt and checked.";
      $("checks").innerHTML = "";
      $("actions").innerHTML = "";
      poll();
    }

    async function checkout() {
      const button = $("checkout");
      setLoading(button, true);
      try {
        const response = await fetch(`/api/jobs/${jobId}/paypal/order`, { method: "POST" });
        const order = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(order.detail || "PayPal could not create the order.");
        showError("");
        if (order.approve_url) {
          $("status-copy").textContent = "PayPal is opening securely. Approve the itemized bill there, then return here to confirm payment.";
          window.location.assign(order.approve_url);
          return;
        }
        const refreshed = await fetch(`/api/jobs/${jobId}`);
        renderResults(refreshed.ok ? await refreshed.json() : { status: "PAYMENT_PENDING", payment_order_id: order.id, payment_approval_url: order.approve_url, payment_mode: order.mode, runs: [] });
      } catch (error) {
        showError(error.message || "Could not start PayPal checkout. Check the connection and try again.");
      } finally {
        if (button.isConnected) setLoading(button, false);
      }
    }

    async function resetCheckout(button) {
      setLoading(button, true);
      try {
        const response = await fetch(`/api/jobs/${jobId}/paypal/reset`, { method: "POST" });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || "The PayPal order could not be reset.");
        renderResults(result);
        showError("The previous order was abandoned by this app. After fixing the Sandbox seller currency preference, create a fresh PayPal order.");
      } catch (error) {
        setLoading(button, false);
        showError(error.message);
      }
    }

    async function capturePayment(orderId, button) {
      if (!orderId) { showError("No PayPal order is attached to this job."); return; }
      if (button) setLoading(button, true);
      try {
        const response = await fetch(`/api/jobs/${jobId}/paypal/capture`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ order_id: orderId })
        });
        const result = await response.json();
        if (!response.ok) {
          if (button) setLoading(button, false);
          showError(result.detail || "PayPal capture was not confirmed.");
          return;
        }
        showError("");
        const refreshed = await fetch(`/api/jobs/${jobId}`);
        if (refreshed.ok) renderResults(await refreshed.json());
        confetti();
      } catch (error) {
        if (button) setLoading(button, false);
        showError("Could not reach the server to confirm PayPal capture. Check your connection and retry.");
      }
    }

    async function resumePaypalReturn() {
      const params = new URLSearchParams(window.location.search);
      const outcome = params.get("paypal");
      if (!outcome) return;
      const returnedJobId = params.get("job_id");
      window.history.replaceState({}, "", window.location.pathname);
      if (outcome === "invalid" || !returnedJobId) {
        showError("PayPal returned without a matching job. Reopen the order from the verified job page.");
        return;
      }
      jobId = returnedJobId;
      $("progress").classList.remove("hidden");
      try {
        const response = await fetch(`/api/jobs/${jobId}`);
        if (!response.ok) throw new Error("Job not found");
        const job = await response.json();
        renderResults(job);
        if (outcome === "approved" && job.status === "PAYMENT_PENDING") {
          await capturePayment(job.payment_order_id, null);
        } else if (outcome === "cancelled") {
          let diagnostic = null;
          if (job.payment_order_id) {
            try {
              diagnostic = await loadPaypalDiagnostics();
            } catch (_) { /* Keep the cancellation state useful if PayPal lookup is unavailable. */ }
          }
          const currency = esc(diagnostic?.currency || job.currency || "USD");
          const orderDetails = diagnostic
            ? ` PayPal order details: ${esc(diagnostic.amount || "unknown")} ${currency}, status ${esc(diagnostic.status || "unknown")}.`
            : "";
          const merchant = diagnostic?.payee_merchant_id
            ? ` PayPal identifies the order's Sandbox seller as merchant ID ${esc(diagnostic.payee_merchant_id)}. Compare that ID with the Test Store account where you enabled currency conversion; if they differ, use the REST app credentials from that Test Store in the app's Sandbox configuration.`
            : " I could not retrieve the Sandbox seller ID for this order, so verify that the API credentials belong to the Test Store account whose receiving preferences you updated.";
          showError(`PayPal did not complete or capture this payment. The order is for ${currency}.${orderDetails} Your screenshot confirms conversion is enabled, so the next check is the seller attached to the order.${merchant} If the IDs match and PayPal still reports UNSUPPORTED_PAYEE_CURRENCY, the Sandbox seller or region is rejecting that currency; PayPal must allow it for that account. Retry only after resolving the seller/currency mismatch.`);
        }
      } catch (error) {
        showError("Could not restore this job after PayPal returned. Refresh the page and retry.");
      }
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

    resumePaypalReturn();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
