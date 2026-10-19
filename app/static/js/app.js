const $ = (id) => document.getElementById(id);
let jobId = null;

function showError(message) { $("error").textContent = message; }

function renderContract(job) {
  $("contract-price").textContent = `$${job.price.toFixed(2)} ${job.currency}`;
  $("criteria").innerHTML = job.contract.criteria.map((criterion) => `<div class="criterion"><span class="check">✓</span><div><strong>${criterion.label}</strong><small>${criterion.detail}</small></div></div>`).join("");
  $("contract").classList.remove("hidden");
  $("contract").scrollIntoView({ behavior: "smooth", block: "center" });
}

$("create").onclick = async () => {
  showError("");
  try {
    const response = await fetch("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt: $("prompt").value, budget: Number($("budget").value) }) });
    if (!response.ok) throw new Error("Please add a little more detail to your brief.");
    const job = await response.json(); jobId = job.id; renderContract(job);
  } catch (error) { showError(error.message); }
};

$("approve").onclick = async () => {
  const approved = await fetch(`/api/jobs/${jobId}/approve-spec`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approved: true }) });
  if (!approved.ok) { showError("The acceptance contract could not be approved."); return; }
  $("contract").classList.add("hidden"); $("progress").classList.remove("hidden");
  await fetch(`/api/jobs/${jobId}/run`, { method: "POST" }); poll();
};

async function poll() {
  const job = await (await fetch(`/api/jobs/${jobId}`)).json();
  if (["SPEC_APPROVED", "GENERATING", "VERIFYING", "REPAIRING"].includes(job.status)) { setTimeout(poll, 500); return; }
  renderResults(job);
}

function renderResults(job) {
  const latest = job.runs.at(-1);
  $("status-title").textContent = job.status === "VERIFIED" ? "Verified. Ready for checkout." : "Verification needs attention";
  $("status-copy").textContent = job.status === "VERIFIED" ? "Every acceptance criterion passed independently." : "The contractor could not satisfy every approved check.";
  $("status-dot").style.background = job.status === "VERIFIED" ? "#9bc152" : "#db6d5f";

  // Show verification results with evidence
  $("checks").innerHTML = latest ? latest.results.map((result) => `
    <div class="result">
      <div>
        <span>${result.label}</span>
        ${result.evidence ? `<small class="muted">${result.evidence}</small>` : ''}
      </div>
      <span class="pass">${result.passed ? "PASS" : "FAIL"}</span>
    </div>
  `).join("") : "";

  // Add preview buttons
  let buttons = "";
  if (job.status === "VERIFIED") {
    buttons += `<button class="primary" id="checkout">Create PayPal Sandbox order <span>→</span></button>`;
  }
  if (latest && latest.results.length > 0) {
    buttons += `<button class="secondary" id="preview-annotated" style="margin-top: 10px;">View Annotated Preview <span>→</span></button>`;
  }
  if (job.runs.length > 1) {
    buttons += `<button class="secondary" id="view-versions" style="margin-top: 10px;">View Version History <span>→</span></button>`;
  }

  $("actions").innerHTML = buttons || `<p class="muted">The payment gate remains closed until every approved criterion passes.</p>`;
  $("progress").scrollIntoView({ behavior: "smooth", block: "center" });

  if ($("checkout")) $("checkout").onclick = checkout;
  if ($("preview-annotated")) $("preview-annotated").onclick = () => window.open(`/api/jobs/${jobId}/preview/annotated`, '_blank');
  if ($("view-versions")) $("view-versions").onclick = viewVersions;
}

async function checkout() {
  const response = await fetch(`/api/jobs/${jobId}/paypal/order`, { method: "POST" });
  const order = await response.json();
  if (!response.ok) { showError(order.detail || "PayPal could not create the order."); return; }
  const approval = order.approve_url ? `<a class="primary" href="${order.approve_url}" target="_blank" rel="noopener">Open PayPal Sandbox approval ↗</a>` : `<p class="muted">Mock order mode is active; no external approval is required.</p>`;
  $("actions").innerHTML = `<p class="muted">Order <strong>${order.id}</strong> created for $${order.amount} ${order.currency}. Complete buyer approval, then confirm capture below.</p>${approval}<button class="primary" id="capture">Confirm server-side capture <span>→</span></button>`;
  $("capture").onclick = async () => {
    const captured = await fetch(`/api/jobs/${jobId}/paypal/capture`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ order_id: order.id }) });
    const result = await captured.json();
    if (!captured.ok) { showError(result.detail || "PayPal capture was not confirmed."); return; }
    $("actions").innerHTML = `<p class="muted">Payment <strong>${result.capture_id}</strong> was confirmed by the server.</p><button class="primary" id="download">Download verified source ZIP <span>↓</span></button>`;
    $("download").onclick = () => { window.location = `/api/jobs/${jobId}/download`; };
  };
}

async function viewVersions() {
  const response = await fetch(`/api/jobs/${jobId}/versions`);
  const versions = await response.json();
  if (!response.ok) { showError("Could not load version history."); return; }

  const versionHtml = versions.map(v => `
    <div class="version-item">
      <span>Attempt ${v.attempt}</span>
      <span class="${v.passed ? 'pass' : 'fail'}">${v.pass_count}/${v.check_count} checks passed</span>
      ${v.has_browser_results ? '<span class="muted">• Browser tested</span>' : ''}
    </div>
  `).join('');

  $("checks").innerHTML = `<h3>Version History</h3><div class="version-list">${versionHtml}</div>`;
}
