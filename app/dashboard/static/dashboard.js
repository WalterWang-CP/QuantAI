"use strict";
const $ = id => document.getElementById(id);
const categories = {
  filings: ["Filings", ["form_type", "report_period", "filed_date", "accession_number"]],
  shares: ["Reviewed shares", ["observation_date", "known_date", "shares_text", "status", "reason"]],
  mappings: ["Share mappings", ["security_id", "valid_from", "valid_to", "known_date"]],
  securities: ["Securities", ["name", "security_type", "start_date", "end_date"]],
  listings: ["Listings", ["ticker", "exchange_code", "currency_code", "start_date", "end_date"]],
  prices: ["Prices", ["trading_date", "open_price", "high_price", "low_price", "close_price", "volume"]],
  snapshots: ["Market-cap snapshots", ["valuation_date", "created_at", "input_hash"]],
  artifacts: ["SEC archives", ["sha256", "byte_count", "fetched_at", "source_url"]],
  facts: ["Raw facts", ["taxonomy", "tag", "period_end", "unit", "value_text"]],
  "csv-archives": ["CSV archives", ["source_id", "sha256", "byte_count"]]
};
let company = null, category = "filings", offset = 0, companyOffset = 0, search = "";
let generation = 0, recordsSequence = 0, detailSequence = 0, companiesSequence = 0, sourcesSequence = 0;
let sources = [];
const PAGE = 50;
function status(id, message, error = false) { $(id).textContent = message; $(id).classList.toggle("error", error); }
async function api(path) {
  const response = await fetch(path, {headers: {Accept: "application/json"}, cache: "no-store"});
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { const body = await response.json(); message += ": " + (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)); } catch (_) { /* retain status */ }
    throw new Error(message);
  }
  return response.json();
}
const companyPath = () => `/dashboard/api/companies/${encodeURIComponent(company.id)}`;
function clearDetail() {
  detailSequence++; $("detail").textContent = "No record selected.";
  $("detail-label").textContent = "Choose Inspect beside a record. Snapshot inspection shows the captured calculation, not a new calculation.";
  $("detail-actions").replaceChildren();
}
function clearRecords() {
  recordsSequence++; $("table").replaceChildren(); $("page-label").textContent = "";
  $("prev").disabled = true; $("next").disabled = true; clearDetail();
}
function options(id, rows, value, label) {
  $(id).replaceChildren();
  for (const row of rows) { const option = document.createElement("option"); option.value = row[value]; option.textContent = label(row); $(id).append(option); }
  $(id).disabled = rows.length === 0;
}
async function loadCompanies() {
  const sequence = ++companiesSequence;
  $("companies").replaceChildren(); $("company-prev").disabled = true; $("company-next").disabled = true;
  status("company-status", "Loading companies…");
  try {
    const result = await api("/dashboard/api/companies?" + new URLSearchParams({q: search, limit: 25, offset: companyOffset}));
    if (sequence !== companiesSequence) return;
    status("company-status", result.items.length ? `Showing ${companyOffset + 1}–${companyOffset + result.items.length}` : "No matching companies.");
    for (const row of result.items) {
      const button = document.createElement("button"); button.className = "company"; button.dataset.company = row.id;
      button.classList.toggle("active", company?.id === row.id);
      const name = document.createElement("span"); name.textContent = row.legal_name;
      const note = document.createElement("small"); note.textContent = `${row.country_code || "Country unspecified"} · ${row.is_active ? "Active" : "Inactive"}`;
      button.append(name, note); button.addEventListener("click", () => chooseCompany(row)); $("companies").append(button);
    }
    $("company-prev").disabled = companyOffset === 0; $("company-next").disabled = !result.has_more;
  } catch (error) { if (sequence === companiesSequence) status("company-status", error.message, true); }
}
function chooseCompany(row) {
  company = row; generation++; sourcesSequence++; offset = 0; sources = [];
  $("company-name").textContent = row.legal_name; $("company-id").textContent = row.id; $("refresh").disabled = false;
  document.querySelectorAll(".company").forEach(button => button.classList.toggle("active", button.dataset.company === row.id));
  options("listing", [], "id", () => ""); options("source", [], "source_id", () => "");
  $("start").value = ""; $("end").value = ""; $("source-summary").textContent = "";
  clearRecords(); loadListings(); loadRecords();
}
async function loadListings() {
  const token = generation, path = companyPath();
  try {
    let rows = [], cursor = 0, more = true;
    while (more) {
      const result = await api(`${path}/listings?limit=200&offset=${cursor}`);
      if (token !== generation) return;
      rows.push(...result.items); more = result.has_more; cursor += result.items.length;
    }
    options("listing", rows, "id", row => `${row.ticker} · ${row.exchange_code} · ${row.currency_code} (${row.start_date}–${row.end_date || "open"})`);
    if (!rows.length) { if (category === "prices") status("record-status", "No listings stored for this company."); return; }
    loadSources();
  } catch (error) { if (token === generation) status("record-status", "Could not load listing choices: " + error.message, true); }
}
async function loadSources() {
  const token = generation, sequence = ++sourcesSequence, listing = $("listing").value;
  options("source", [], "source_id", () => ""); sources = []; $("source-summary").textContent = "";
  if (category === "prices") { clearRecords(); status("record-status", "Loading price sources…"); }
  if (!listing) return;
  try {
    const result = await api(`${companyPath()}/listings/${encodeURIComponent(listing)}/sources`);
    if (token !== generation || sequence !== sourcesSequence) return;
    sources = result;
    options("source", sources, "source_id", row => `${row.provider_name} / ${row.dataset_name}`);
    updateSourceSummary(); if (category === "prices") { offset = 0; loadRecords(); }
  } catch (error) { if (token === generation && sequence === sourcesSequence) status("record-status", error.message, true); }
}
function updateSourceSummary() {
  const source = sources.find(row => row.source_id === $("source").value);
  $("source-summary").textContent = source ? `${source.rows} stored rows · ${source.first_date} through ${source.last_date}. This range does not establish complete trading-day coverage.` : "No stored price sources for this listing.";
}
async function inspect(row, selectedCategory, selectedCompany) {
  const sequence = ++detailSequence;
  $("detail-actions").replaceChildren(); $("detail").textContent = "Loading evidence…";
  $("detail-label").textContent = `${categories[selectedCategory][0]} · ${row.id}`;
  try {
    const result = selectedCategory === "snapshots" ? await api(`/dashboard/api/companies/${encodeURIComponent(selectedCompany)}/snapshots/${encodeURIComponent(row.id)}`) : row;
    if (sequence !== detailSequence) return;
    $("detail").textContent = JSON.stringify(result, null, 2);
    const archiveId = selectedCategory === "csv-archives" ? row.id : result.manifest?.price?.csv_artifact_id;
    if (archiveId) {
      const link = document.createElement("a"); link.textContent = "Download captured CSV";
      link.href = `/market-data/csv-artifacts/${encodeURIComponent(archiveId)}`; link.setAttribute("download", ""); $("detail-actions").append(link);
    }
  } catch (error) { if (sequence === detailSequence) $("detail").textContent = error.message; }
}
function renderTable(items) {
  const selectedCategory = category, selectedCompany = company.id;
  const table = document.createElement("table"), head = document.createElement("thead"), heading = document.createElement("tr"), body = document.createElement("tbody");
  for (const column of [...categories[category][1], "Evidence"]) { const th = document.createElement("th"); th.textContent = column.replaceAll("_", " "); th.scope = "col"; heading.append(th); }
  head.append(heading);
  for (const row of items) {
    const tr = document.createElement("tr");
    for (const column of categories[category][1]) { const td = document.createElement("td"); td.textContent = row[column] == null ? "—" : String(row[column]); tr.append(td); }
    const td = document.createElement("td"), button = document.createElement("button"); button.textContent = "Inspect";
    button.addEventListener("click", () => inspect(row, selectedCategory, selectedCompany)); td.append(button); tr.append(td); body.append(tr);
  }
  table.append(head, body); $("table").replaceChildren(table);
}
async function loadRecords() {
  clearRecords(); $("category").textContent = categories[category][0];
  if (!company) return;
  const sequence = recordsSequence, token = generation;
  let path = `${companyPath()}/${category}`, params = new URLSearchParams({limit: PAGE, offset});
  if (category === "prices") {
    if (!$("listing").value || !$("source").value) { status("record-status", sourcesSequence ? "No price source selected. Choose a listing with stored prices; choices may still be loading." : "Choose a listing and source."); return; }
    if ($("start").value && $("end").value && $("start").value > $("end").value) { status("record-status", "From date must be on or before Through date.", true); return; }
    path = `${companyPath()}/listings/${encodeURIComponent($("listing").value)}/prices`;
    params.set("source_id", $("source").value);
    for (const field of ["start", "end"]) if ($(field).value) params.set(field, $(field).value);
  }
  status("record-status", "Loading records…");
  try {
    const result = await api(path + "?" + params);
    if (sequence !== recordsSequence || token !== generation) return;
    status("record-status", result.items.length ? "Stored records · Select Inspect to see IDs and evidence." : "No stored records match this selection. Missing records do not establish coverage or pilot completion.");
    if (result.items.length) renderTable(result.items);
    $("page-label").textContent = result.items.length ? `${offset + 1}–${offset + result.items.length}` : "";
    $("prev").disabled = offset === 0; $("next").disabled = !result.has_more;
  } catch (error) { if (sequence === recordsSequence && token === generation) status("record-status", error.message, true); }
}
for (const [key, [label]] of Object.entries(categories)) {
  const button = document.createElement("button"); button.textContent = label; button.classList.toggle("active", key === category); button.setAttribute("aria-pressed", String(key === category));
  button.addEventListener("click", () => {
    category = key; offset = 0; $("price-controls").hidden = key !== "prices";
    for (const child of $("tabs").children) { child.classList.toggle("active", child === button); child.setAttribute("aria-pressed", String(child === button)); }
    loadRecords();
  }); $("tabs").append(button);
}
function runSearch() { search = $("search").value; companyOffset = 0; loadCompanies(); }
$("search-button").addEventListener("click", runSearch);
$("search").addEventListener("keydown", event => { if (event.key === "Enter") runSearch(); });
$("company-prev").addEventListener("click", () => { companyOffset = Math.max(0, companyOffset - 25); loadCompanies(); });
$("company-next").addEventListener("click", () => { companyOffset += 25; loadCompanies(); });
$("prev").addEventListener("click", () => { offset = Math.max(0, offset - PAGE); loadRecords(); });
$("next").addEventListener("click", () => { offset += PAGE; loadRecords(); });
$("listing").addEventListener("change", () => { offset = 0; loadSources(); });
$("source").addEventListener("change", () => { offset = 0; updateSourceSummary(); loadRecords(); });
$("filter").addEventListener("click", () => { offset = 0; loadRecords(); });
$("refresh").addEventListener("click", () => { if (company) chooseCompany(company); });
$("clear").addEventListener("click", clearDetail);
loadCompanies();
