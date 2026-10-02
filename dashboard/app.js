"use strict";

const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const number = (value) => Number(value).toLocaleString();
const statementName = (value) => ({BalanceSheet:"Balance sheet",IncomeStatement:"Income statement",CashFlow:"Cash flow"}[value] || value);
const tierName = (value) => ({"linkbase-verified":"Linkbase verified","expert-authored-UNVALIDATED":"Expert authored · unvalidated","expert-authored":"Expert authored","no-governing-paragraph":"Detection only","unresolved":"Unresolved"}[value] || value);
const decisionName = (value) => ({pending:"Awaiting review",approved:"Answer approved",flagged:"Flagged for follow-up",rejected:"Answer rejected"}[value]);
const filterFields = ["company","fiscal_year","statement_type","tiers","rules","error_types","citations","form","kind"];
const pageSize = 40;
const state = {dataset:"us-gaap",index:null, reviews:{}, filtered:[], queue:"all", page:0, id:null, detail:null, tab:"statement", corrected:false, highlight:true, searchIds:null, loading:false};
let datasetSequence = 0, detailSequence = 0, searchSequence = 0, searchTimer, toastTimer;

function toast(message, error = false) {
  clearTimeout(toastTimer);
  $("#toast").textContent = message;
  $("#toast").className = `toast${error ? " error" : ""}`;
  $("#toast").hidden = false;
  toastTimer = setTimeout(() => { $("#toast").hidden = true; }, error ? 9000 : 4500);
}

async function api(path, params = {}) {
  const response = await fetch(`/api/${path}?${new URLSearchParams({dataset:state.dataset,...params})}`);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function storageKey() { return `intelliaudit.review.v1.${state.dataset}.${state.index.fingerprint}`; }
function validReview(review) {
  return review && typeof review === "object" && ["pending","approved","flagged","rejected"].includes(review.status)
    && ["notes","citation","judgement","reviewer","updated_at"].every((k) => review[k] === undefined || typeof review[k] === "string")
    && (review.notes?.length || 0) <= 20000 && (review.citation?.length || 0) <= 500
    && (review.reviewer?.length || 0) <= 200
    && [undefined,"","Correct","Incorrect","Uncertain"].includes(review.judgement)
    && (!review.updated_at || Number.isFinite(Date.parse(review.updated_at)));
}
function readReviews() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey()) || "{}");
    // Keep earlier reviews outside the smaller cohort so saving does not erase them.
    return Object.fromEntries(Object.entries(saved).filter(([, r]) => validReview(r)));
  } catch {
    toast("Browser storage is unavailable or unreadable. Export your reviews to keep a copy.", true);
    return {};
  }
}
function persist() {
  try { localStorage.setItem(storageKey(), JSON.stringify(state.reviews)); return true; }
  catch { toast("Could not save in this browser. Your work is in memory; export it before leaving.", true); return false; }
}
function statusOf(id) { return state.reviews[id]?.status || "pending"; }

async function loadDataset(dataset, requestedId = null) {
  const sequence = ++datasetSequence;
  ++detailSequence;
  ++searchSequence;
  clearTimeout(searchTimer);
  state.dataset = dataset;
  state.loading = true;
  state.index = null;
  state.reviews = {};
  state.id = null;
  state.detail = null;
  state.searchIds = null;
  state.corrected = false;
  state.tab = "statement";
  $("#dataset").value = dataset;
  $("#search").value = "";
  $("#export-button").disabled = true;
  $("#import-button").disabled = true;
  $("#case-list").innerHTML = "";
  $("#case-detail").innerHTML = '<div class="empty-state"><div class="empty-icon">▤</div><h2>Loading your workspace</h2><p>Reading the benchmark and answer key…</p></div>';
  $("#result-count").textContent = "Loading cases…";
  $("#page-info").textContent = "—";
  $("#page-prev").disabled = $("#page-next").disabled = true;
  ["total","pending","approved","flagged"].forEach((k) => { $(`#stat-${k}`).textContent = "—"; });
  $("#stat-scope").textContent = "Loading benchmark…";
  try {
    const index = await api("index");
    if (sequence !== datasetSequence) return;
    state.index = index;
    state.reviews = readReviews();
    state.loading = false;
    $("#export-button").disabled = false;
    $("#import-button").disabled = false;
    populateFilters();
    renderSummary();
    applyFilters(requestedId);
  } catch (error) {
    if (sequence !== datasetSequence) return;
    state.loading = false;
    $("#result-count").textContent = "Dataset unavailable";
    $("#case-detail").innerHTML = `<div class="empty-state"><div class="empty-icon">!</div><h2>Could not load this dataset</h2><p>${esc(error.message)}</p><button id="retry-load" class="button secondary">Try again</button></div>`;
    $("#retry-load").onclick = () => loadDataset(dataset);
  }
}

function populateFilters() {
  const defaults = {company:"All companies",fiscal_year:"All years",statement_type:"All statements",tiers:"All tiers",rules:"All rules",error_types:"All error types",citations:"All paragraphs",form:"All forms",kind:"All types"};
  filterFields.forEach((field) => {
    const options = state.index.facets[field];
    $(`#filter-${field}`).innerHTML = `<option value="">${defaults[field]}</option>` + options.map((value) => {
      const label = field === "statement_type" ? statementName(value) : field === "tiers" ? tierName(value) : field === "kind" ? (value === "control" ? "Clean control" : "Injected fault") : value;
      return `<option value="${esc(value)}">${esc(label)}</option>`;
    }).join("");
  });
}

function renderSummary() {
  if (!state.index) return;
  const counts = {pending:0,approved:0,flagged:0,rejected:0};
  state.index.cases.forEach((c) => { counts[statusOf(c.id)]++; });
  const total = state.index.cases.length;
  const reviewed = total - counts.pending;
  $("#stat-total").textContent = number(total);
  $("#tab-total").textContent = number(total);
  $("#stat-scope").textContent = `${number(state.index.facets.company.length)} companies · ${state.index.name}`;
  ["pending","approved","flagged"].forEach((key) => {
    $(`#stat-${key}`).textContent = number(counts[key]);
    $(`#nav-${key}`).textContent = number(counts[key]);
  });
  $("#nav-rejected").textContent = number(counts.rejected);
  $("#stat-approved-detail").textContent = counts.rejected ? `${number(counts.rejected)} answers rejected separately` : "Validated by you";
  const percent = total ? (reviewed / total * 100).toFixed(1) : "0.0";
  $("#progress-text").textContent = `${percent}% reviewed`;
  $("#review-progress").value = percent;
  document.querySelectorAll("[data-queue]").forEach((button) => {
    button.classList.toggle(button.classList.contains("nav-item") ? "active" : "selected", button.dataset.queue === state.queue);
  });
}

function applyFilters(preferredId = null, keepSelection = false) {
  if (!state.index) return;
  const filters = filterFields.map((f) => [f, $(`#filter-${f}`).value]).filter(([,v]) => v !== "");
  $("#filter-count").textContent = filters.filter(([f]) => ["rules","error_types","citations","form","kind"].includes(f)).length || "";
  state.filtered = state.index.cases.filter((c) => {
    if (state.queue !== "all" && statusOf(c.id) !== state.queue) return false;
    if (state.searchIds && !state.searchIds.has(c.id)) return false;
    return filters.every(([field, value]) => Array.isArray(c[field]) ? c[field].includes(value) : String(c[field]) === value);
  });
  const sort = $("#sort").value;
  state.filtered.sort((a,b) => {
    if (sort === "year" && a.fiscal_year !== b.fiscal_year) return b.fiscal_year - a.fiscal_year;
    if (sort === "tier") {
      const rank = (c) => c.tiers.some((t) => t.includes("UNVALIDATED")) ? 0 : c.tiers.includes("unresolved") ? 1 : 2;
      if (rank(a) !== rank(b)) return rank(a) - rank(b);
    }
    return a.company.localeCompare(b.company) || b.fiscal_year - a.fiscal_year || a.statement_type.localeCompare(b.statement_type) || a.id.localeCompare(b.id);
  });
  const selected = preferredId || (keepSelection && state.id);
  const position = state.filtered.findIndex((c) => c.id === selected);
  state.page = position >= 0 ? Math.floor(position / pageSize) : 0;
  renderQueue();
  const nextId = position >= 0 ? selected : state.filtered[0]?.id;
  if (nextId) {
    if (nextId !== state.id || !state.detail) selectCase(nextId);
  } else {
    ++detailSequence;
    state.id = null;
    state.detail = null;
    $("#case-detail").innerHTML = '<div class="empty-state"><div class="empty-icon">⌕</div><h2>No cases match these filters</h2><p>Try a different search or reset the filters.</p></div>';
  }
}

function caseTag(c) {
  if (c.kind === "control") return '<span class="badge teal">Clean control</span>';
  return `<span class="badge ${c.citable ? "blue" : ""}">${c.error_count > 1 ? `${c.error_count} faults` : esc(c.error_types[0] || "Injected fault")}</span>`;
}
function renderQueue() {
  const total = state.filtered.length;
  const start = state.page * pageSize;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  $("#result-count").textContent = `${number(total)} case${total === 1 ? "" : "s"}`;
  $("#page-info").textContent = `${state.page + 1} / ${pages}`;
  $("#page-prev").disabled = state.page === 0;
  $("#page-next").disabled = state.page >= pages - 1;
  $("#case-list").innerHTML = state.filtered.slice(start,start+pageSize).map((c) => {
    const status = statusOf(c.id);
    const tier = c.tiers.some((t) => t.includes("UNVALIDATED")) ? '<span class="badge amber">Unvalidated</span>' : c.tiers.includes("linkbase-verified") ? '<span class="badge teal">Verified</span>' : "";
    return `<button class="case-card${c.id === state.id ? " selected" : ""}" data-id="${esc(c.id)}" aria-current="${c.id === state.id}" aria-label="${esc(c.company)}, FY ${c.fiscal_year}, ${esc(statementName(c.statement_type))}, ${esc(c.id)}, ${decisionName(status)}"><div class="case-card-top"><span class="company-name">${esc(c.company)}</span><span class="status-dot ${status}" title="${decisionName(status)}"></span></div><div class="case-card-meta">FY ${c.fiscal_year} <span>·</span> ${esc(statementName(c.statement_type))}</div><div class="case-card-tags">${caseTag(c)}${tier}${status !== "pending" ? `<span class="badge ${status === "approved" ? "teal" : status === "flagged" ? "amber" : "red"}">${status}</span>` : ""}</div><div class="case-card-id">${esc(c.id)}</div></button>`;
  }).join("") || '<div class="empty-state"><p>No matching cases</p></div>';
  document.querySelectorAll(".case-card").forEach((b) => { b.onclick = () => selectCase(b.dataset.id); });
}

async function selectCase(id) {
  const sequence = ++detailSequence;
  state.id = id;
  state.detail = null;
  renderQueue();
  history.replaceState(null, "", `#${new URLSearchParams({dataset:state.dataset,case:id})}`);
  $("#case-detail").innerHTML = '<div class="empty-state"><div class="empty-icon">▤</div><p>Loading case evidence…</p></div>';
  try {
    const detail = await api("case", {id});
    if (sequence !== detailSequence) return;
    state.detail = detail;
    renderDetail();
  } catch (error) {
    if (sequence !== detailSequence) return;
    $("#case-detail").innerHTML = `<div class="empty-state"><h2>Case unavailable</h2><p>${esc(error.message)}</p><button id="retry-case" class="button secondary">Try again</button></div>`;
    $("#retry-case").onclick = () => selectCase(id);
  }
}

function parseRows(text) {
  return Array.from(String(text || "").matchAll(/\[row\s+(\d+)\]:\s*([\s\S]*?)(?=\s*\[SEP\]|\[row\s+\d+\]:|$)/g), (match) => {
    const parts = match[2].trim().split("|");
    return {row:Number(match[1]),label:parts[0].trim(),amount:parts.slice(1).join("|").trim()};
  });
}
function markedRows() {
  if (!state.highlight) return new Set();
  return new Set(state.detail.errors.map((e) => {
    if (state.corrected) return e.pre_inject_row ?? null;
    // A removed row does not exist in the given version; its index now belongs to a different line.
    if (Object.hasOwn(e, "post_inject_row") && e.post_inject_row === null) return null;
    return e.post_inject_row ?? e.problematic_entry;
  }).filter((v) => Number.isInteger(v)));
}
function displayAmount(amount, unit) {
  // The renderer uses "$" for all frameworks. Keep source values; label with the actual ISO currency.
  const currency = unit?.split(" ")[0] || "USD";
  return currency !== "USD" ? amount.replaceAll("$", "") : amount;
}

function statementView() {
  const {exam,answer} = state.detail;
  const text = state.corrected ? answer.corrected_statement_text : exam.statement_text;
  const marks = markedRows();
  const rows = parseRows(text);
  return `<div class="section-heading"><h3>${esc(statementName(exam.metadata.statement_type))}</h3><div class="segmented" role="group" aria-label="Statement version"><button id="given-view" class="${!state.corrected ? "active" : ""}" aria-pressed="${!state.corrected}">As given</button><button id="corrected-view" class="${state.corrected ? "active" : ""}" aria-pressed="${state.corrected}">Corrected</button></div></div><div class="statement-caption"><span>${esc(exam.metadata.period)} · ${esc(exam.metadata.unit)}</span><label class="highlight-toggle"><input id="highlight" type="checkbox" ${state.highlight ? "checked" : ""}> Highlight key rows</label></div><div class="table-wrap"><table class="statement-table"><thead><tr><th scope="col">ROW</th><th scope="col">LINE ITEM</th><th scope="col">AMOUNT</th></tr></thead><tbody>${rows.map((r) => `<tr class="${!r.amount ? "section " : ""}${/^(Total|Net |Operating income|Income before)/i.test(r.label) ? "total " : ""}${marks.has(r.row) ? "highlight" : ""}"${marks.has(r.row) ? ' title="Affected row named in the proposed answer key"' : ""}><td>${r.row}</td><td>${esc(r.label)}</td><td>${esc(displayAmount(r.amount,exam.metadata.unit))}</td></tr>`).join("")}</tbody></table></div><div class="table-legend"><span class="legend-square"></span> Highlighted rows are identified by the answer key</div><p class="currency-note">Amounts in ${esc(exam.metadata.unit)}. ${state.corrected ? "Proposed corrected statement from the answer key." : "Statement as presented to the auditor."} Row numbers start at 0.</p>`;
}

function evidenceView() {
  const text = state.detail.exam.transaction_data || "";
  const [transactions, supporting = ""] = text.split(/Supporting facts \(period-end reviews\):/);
  const lines = transactions.split("\n").filter((l) => l.trim());
  const intro = lines.shift() || "";
  const blocks = lines.map((line) => {
    const match = line.match(/^\[([^\]]+)\]\s*([\s\S]*)/);
    return `<article class="evidence-block"><h4>${esc(match?.[1] || "Transaction")}</h4><p>${esc(match?.[2] || line)}</p></article>`;
  }).join("");
  return `<div class="section-heading"><h3>Transaction evidence</h3><span class="badge blue">Synthetic movements</span></div><div class="evidence-note">${esc(intro || "No transaction evidence supplied for this case.")}</div>${blocks}${supporting ? `<h3 class="raw-heading">Period-end supporting facts</h3>${supporting.trim().split(/\n-\s*/).filter(Boolean).map((fact) => `<article class="evidence-block supporting"><p>${esc(fact.replace(/^-\s*/,""))}</p></article>`).join("")}` : ""}`;
}

function rawView() {
  return `<div class="section-heading"><h3>Original record</h3><span class="badge">Exam + answer key</span></div><pre class="raw-json">${esc(JSON.stringify({exam:state.detail.exam,answer_key:state.detail.answer},null,2))}</pre>`;
}

function answerView() {
  const {answer,errors} = state.detail;
  let content = `<div class="answer-card"><div class="field-label">Proposed judgement</div><div class="current-decision"><span class="badge ${answer.general_judgement === "Correct" ? "teal" : "red"}">${esc(answer.general_judgement)}</span> <span class="badge">${errors.length ? `${errors.length} fault${errors.length > 1 ? "s" : ""}` : "Clean control"}</span></div></div>`;
  content += errors.map((e, i) => {
    const c = e.ground_truth_citations || {};
    const tier = c.citation_tier || "unresolved";
    const row = Object.hasOwn(e,"post_inject_row") && e.post_inject_row === null ? `Missing in given statement · corrected row ${e.pre_inject_row ?? "—"}` : `Given row ${e.post_inject_row ?? e.problematic_entry ?? "—"} · corrected row ${e.pre_inject_row ?? "—"}`;
    return `<article class="answer-card"><h4>${errors.length > 1 ? `${i+1}. ` : ""}${esc(e.error_type || "Fault")}</h4><div class="rule-id">${esc(e.rule_id)}</div><div class="field-label">Affected line item</div><div class="field-value">${esc(e.affected_label || e.injection_detail?.row_label || "Not specified")}</div><div class="field-value">${esc(row)}</div><div class="field-label">Governing paragraph</div><div class="citation-value">${esc(c.asc_full || "No governing paragraph")}</div><div class="current-decision"><span class="badge ${tier.includes("UNVALIDATED") ? "amber" : tier === "linkbase-verified" ? "teal" : ""}">${esc(tierName(tier))}</span></div><p class="rationale">${esc(c.rationale || "No citation rationale supplied.")}</p>${c.note ? `<p class="rationale">${esc(c.note)}</p>` : ""}<details><summary>XBRL concept & reference evidence</summary><div class="field-label">Concept</div><div class="field-value">${esc(e.affected_xbrl_concept || e.injection_detail?.row_concept || "—")}</div><div class="field-label">Linkbase paragraph match</div><div class="field-value">${c.linkbase_verified ? "Verified by the dataset resolver" : "Not verified by the dataset resolver"}</div><ul>${(c.linkbase_reference_set || []).map((r) => `<li>${esc(r)}</li>`).join("") || "<li>No linkbase references supplied</li>"}</ul></details></article>`;
  }).join("");
  if (!errors.length) content += '<div class="answer-card"><h4>No injected fault</h4><p class="rationale">This case is a clean control. Assess the statement and evidence before approving the proposed “Correct” judgement.</p></div>';
  if (answer.self_check) {
    content += `<div class="check-line"><span>${answer.self_check.clean_reconciles ? "✓" : "!"}</span> Clean statement ${answer.self_check.clean_reconciles ? "reconciles" : "does not reconcile"}</div><div class="check-line"><span>${answer.self_check.error_breaks_reconciliation ? "!" : "✓"}</span> ${answer.self_check.error_breaks_reconciliation ? "Injected fault breaks reconciliation" : "No reconciliation break recorded"}</div>`;
  }
  return content;
}

function reviewView() {
  const review = state.reviews[state.id] || {status:"pending"};
  return `<section class="review-form"><h3>Your review</h3><p class="form-intro">Validate the proposed answer and citation.</p><div id="decision-badge" class="badge ${review.status === "approved" ? "teal" : review.status === "flagged" ? "amber" : review.status === "rejected" ? "red" : ""}">${decisionName(review.status)}</div><label>Reviewer<input id="reviewer" type="text" maxlength="200" placeholder="Your name or initials" value="${esc(review.reviewer)}"></label><label>Reviewer judgement<select id="review-judgement"><option value="">No alternative recorded</option><option value="Correct" ${review.judgement === "Correct" ? "selected" : ""}>Correct</option><option value="Incorrect" ${review.judgement === "Incorrect" ? "selected" : ""}>Incorrect</option><option value="Uncertain" ${review.judgement === "Uncertain" ? "selected" : ""}>Uncertain</option></select></label><label>Alternative citation (optional)<input id="review-citation" type="text" maxlength="500" placeholder="e.g. ASC 330-10-35-1B" value="${esc(review.citation)}"></label><label>Review notes<textarea id="review-notes" maxlength="20000" placeholder="Document your reasoning or required follow-up…">${esc(review.notes)}</textarea></label><button id="approve" class="button primary">✓ Approve answer</button><div class="review-buttons"><button id="flag" class="button flag">⚑ Flag</button><button id="reject" class="button reject">× Reject</button></div><button id="save-next" class="button secondary">Save & next case →</button><button id="reopen" class="text-button" ${review.status === "pending" ? "hidden" : ""}>Return to awaiting review</button><span id="save-state" class="save-state">${review.updated_at ? `Saved in this browser · ${esc(new Date(review.updated_at).toLocaleString())}` : "Notes save automatically in this browser."}</span></section>`;
}

function renderDetail() {
  if (!state.detail) return;
  const meta = state.detail.exam.metadata;
  const position = state.filtered.findIndex((c) => c.id === state.id);
  const body = state.tab === "statement" ? statementView() : state.tab === "evidence" ? evidenceView() : rawView();
  $("#case-detail").innerHTML = `<div class="detail-header"><div class="detail-eyebrow"><span>${esc(state.id)} · FORM ${esc(state.detail.exam.form)}</span><div class="case-navigation"><button id="case-prev" class="icon-button" aria-label="Previous case" ${position <= 0 ? "disabled" : ""}>←</button><button id="case-next" class="icon-button" aria-label="Next case" ${position >= state.filtered.length-1 ? "disabled" : ""}>→</button></div></div><h2 class="detail-title">${esc(meta.company)}</h2><div class="detail-meta"><span>FY ${meta.fiscal_year}</span><span>${esc(statementName(meta.statement_type))}</span><span>${esc(meta.period)}</span><span>${esc(meta.unit)}</span><span>CIK ${esc(meta.cik)}</span></div></div><div class="detail-tabs" role="group" aria-label="Case view"><button data-tab="statement" class="${state.tab === "statement" ? "active" : ""}">Statement</button><button data-tab="evidence" class="${state.tab === "evidence" ? "active" : ""}">Transactions & facts</button><button data-tab="raw" class="${state.tab === "raw" ? "active" : ""}">Raw data</button></div><div class="detail-body"><section class="statement-column">${body}</section><aside class="answer-column" aria-label="Answer key and review"><h3 class="answer-heading">PROPOSED ANSWER KEY <span>◎</span></h3>${answerView()}${reviewView()}</aside></div>`;
  $("#case-prev").onclick = () => navigateCase(-1);
  $("#case-next").onclick = () => navigateCase(1);
  document.querySelectorAll("[data-tab]").forEach((button) => { button.onclick = () => { state.tab = button.dataset.tab; renderDetail(); }; });
  if (state.tab === "statement") {
    $("#given-view").onclick = () => { state.corrected = false; renderDetail(); };
    $("#corrected-view").onclick = () => { state.corrected = true; renderDetail(); };
    $("#highlight").onchange = (event) => { state.highlight = event.target.checked; renderDetail(); };
  }
  ["reviewer","review-judgement","review-citation","review-notes"].forEach((id) => { $(`#${id}`).addEventListener("input", () => saveReview()); });
  $("#approve").onclick = () => decide("approved");
  $("#flag").onclick = () => decide("flagged");
  $("#reject").onclick = () => decide("rejected");
  $("#reopen").onclick = () => decide("pending");
  $("#save-next").onclick = () => { saveReview(); navigateCase(1); };
}

function saveReview(status = statusOf(state.id)) {
  if (!state.detail) return;
  state.reviews[state.id] = {status,reviewer:$("#reviewer").value,judgement:$("#review-judgement").value,citation:$("#review-citation").value,notes:$("#review-notes").value,updated_at:new Date().toISOString()};
  const saved = persist();
  $("#save-state").textContent = saved ? "Saved in this browser · just now" : "In memory only · export to keep your work";
  return saved;
}
function decide(status) {
  const saved = saveReview(status);
  renderSummary();
  // Stay on this case when it still belongs to the queue; otherwise advance to a matching case.
  applyFilters(state.id, true);
  if (state.detail) renderDetail();
  if (saved) toast(status === "pending" ? "Case returned to awaiting review." : `${decisionName(status)}. Review saved.`);
}
function navigateCase(direction) {
  const position = state.filtered.findIndex((c) => c.id === state.id);
  const next = state.filtered[position+direction];
  if (!next) { toast("You’ve reached the end of this filtered queue."); return; }
  state.page = Math.floor((position+direction) / pageSize);
  selectCase(next.id);
  $("#case-list").scrollTop = 0;
}

async function searchCases() {
  const sequence = ++searchSequence;
  const dataset = state.dataset;
  const q = $("#search").value.trim();
  if (!q) { state.searchIds = null; applyFilters(state.id, true); return; }
  $("#result-count").textContent = "Searching…";
  try {
    const result = await api("search", {q});
    if (sequence !== searchSequence || dataset !== state.dataset) return;
    state.searchIds = new Set(result.ids);
    applyFilters(state.id, true);
  } catch (error) { if (sequence === searchSequence) { toast(error.message,true); renderQueue(); } }
}

function exportReviews() {
  const ids = new Set(state.index.cases.map((c) => c.id));
  const reviews = Object.entries(state.reviews).filter(([id]) => ids.has(id)).map(([exam_id,review]) => ({exam_id,...review}));
  const data = {schema_version:1,dataset:state.dataset,fingerprint:state.index.fingerprint,exported_at:new Date().toISOString(),reviews};
  const blob = new Blob([JSON.stringify(data,null,2)+"\n"], {type:"application/json"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `intelliaudit-reviews-${state.dataset}-${new Date().toISOString().slice(0,10)}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast(`Exported ${number(reviews.length)} saved review${reviews.length === 1 ? "" : "s"} for ${state.index.name}.`);
}

async function importReviews(file) {
  const dataset = state.dataset;
  const fingerprint = state.index.fingerprint;
  try {
    if (file.size > 20*1024*1024) throw new Error("Review file is too large (maximum 20 MB).");
    const data = JSON.parse(await file.text());
    if (dataset !== state.dataset || fingerprint !== state.index?.fingerprint) throw new Error("Dataset changed while reading the file. Please import again.");
    if (data.schema_version !== 1 || data.dataset !== dataset || data.fingerprint !== fingerprint || !Array.isArray(data.reviews)) throw new Error("This export belongs to a different dataset or version. Select its matching dataset before importing.");
    const ids = new Set(state.index.cases.map((c) => c.id));
    if (data.reviews.some((r) => !r || !ids.has(r.exam_id) || !validReview(r))) throw new Error("This file contains invalid review records. No reviews were imported.");
    let imported = 0;
    data.reviews.forEach(({exam_id,...review}) => {
      const current = state.reviews[exam_id];
      if (!current || (review.updated_at || "") >= (current.updated_at || "")) {
        state.reviews[exam_id] = {status:review.status,reviewer:review.reviewer || "",notes:review.notes || "",citation:review.citation || "",judgement:review.judgement || "",updated_at:review.updated_at || ""};
        imported++;
      }
    });
    const saved = persist(); renderSummary(); applyFilters(state.id,true);
    if (state.detail) renderDetail();
    if (saved) toast(`Imported ${number(imported)} reviews. Newer local reviews were kept.`);
  } catch (error) { toast(error.message, true); }
  finally { $("#import-file").value = ""; }
}

$("#dataset").onchange = (event) => loadDataset(event.target.value);
filterFields.forEach((field) => { $(`#filter-${field}`).onchange = () => applyFilters(state.id,true); });
$("#sort").onchange = () => applyFilters(state.id,true);
$("#search").oninput = () => { clearTimeout(searchTimer); ++searchSequence; searchTimer = setTimeout(searchCases,250); };
$("#more-filters").onclick = () => {
  $("#advanced-filters").hidden = !$("#advanced-filters").hidden;
  $("#more-filters").setAttribute("aria-expanded", String(!$("#advanced-filters").hidden));
};
$("#reset-filters").onclick = () => {
  filterFields.forEach((field) => { $(`#filter-${field}`).value = ""; });
  $("#search").value = ""; ++searchSequence; clearTimeout(searchTimer); state.searchIds = null;
  state.queue = "all"; renderSummary(); applyFilters(state.id,true);
};
document.querySelectorAll("[data-queue]").forEach((button) => { button.onclick = () => { state.queue = button.dataset.queue; renderSummary(); applyFilters(state.id,true); }; });
$("#page-prev").onclick = () => { state.page--; renderQueue(); $("#case-list").scrollTop = 0; };
$("#page-next").onclick = () => { state.page++; renderQueue(); $("#case-list").scrollTop = 0; };
$("#export-button").onclick = exportReviews;
$("#import-button").onclick = () => $("#import-file").click();
$("#import-file").onchange = (event) => { if (event.target.files[0]) importReviews(event.target.files[0]); };
$("#help-button").onclick = () => $("#guide").showModal();
$("#close-guide").onclick = () => $("#guide").close();
function followCaseLink() {
  const params = new URLSearchParams(location.hash.slice(1));
  const dataset = ["us-gaap","multi","ifrs"].includes(params.get("dataset")) ? params.get("dataset") : "us-gaap";
  const id = params.get("case");
  if (!state.index || dataset !== state.dataset) { loadDataset(dataset,id); return; }
  if (id && id !== state.id) {
    filterFields.forEach((field) => { $(`#filter-${field}`).value = ""; });
    $("#search").value = ""; ++searchSequence; clearTimeout(searchTimer);
    state.searchIds = null; state.queue = "all";
    renderSummary(); applyFilters(id);
  }
}
window.addEventListener("hashchange", followCaseLink);
followCaseLink();
