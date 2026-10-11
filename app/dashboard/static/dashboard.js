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
let sources = [], listings = [], operationBusy = false, previewKey = null, previewSequence = 0, previewLoading = false, companyMore = false;
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
  $(id).disabled = operationBusy || rows.length === 0;
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
      const button = document.createElement("button"); button.className = "company"; button.dataset.company = row.id; button.disabled = operationBusy;
      button.classList.toggle("active", company?.id === row.id);
      const name = document.createElement("span"); name.textContent = row.legal_name;
      const note = document.createElement("small"); note.textContent = `${row.country_code || "Country unspecified"} · ${row.is_active ? "Active" : "Inactive"}`;
      button.append(name, note); button.addEventListener("click", () => chooseCompany(row)); $("companies").append(button);
    }
    companyMore = result.has_more; $("company-prev").disabled = operationBusy || companyOffset === 0; $("company-next").disabled = operationBusy || !companyMore;
  } catch (error) { if (sequence === companiesSequence) status("company-status", error.message, true); }
}
function chooseCompany(row) {
  if (operationBusy) return;
  resetOperations(); listings = []; $("operations").hidden = false; $("listing-controls").hidden = false;
  company = row; generation++; sourcesSequence++; offset = 0; sources = [];
  $("company-name").textContent = row.legal_name; $("company-id").textContent = row.id; $("refresh").disabled = false;
  document.querySelectorAll(".company").forEach(button => button.classList.toggle("active", button.dataset.company === row.id));
  options("listing", [], "id", () => ""); options("source", [], "source_id", () => "");
  $("start").value = ""; $("end").value = ""; $("source-summary").textContent = "";
  clearRecords(); updateOperationAvailability(); loadListings(); loadRecords();
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
    listings = rows;
    options("listing", rows, "id", row => `${row.ticker} · ${row.exchange_code} · ${row.currency_code} (${row.start_date}–${row.end_date || "open"})`);
    listingChanged();
    if (!rows.length) { if (category === "prices") status("record-status", "No listings stored for this company."); return; }
    loadSources();
  } catch (error) { if (token === generation) status("record-status", "Could not load listing choices: " + error.message, true); }
}
async function loadSources(preferredSource = null) {
  const token = generation, sequence = ++sourcesSequence, listing = $("listing").value;
  options("source", [], "source_id", () => ""); sources = []; $("source-summary").textContent = ""; invalidatePreview(); updateOperationAvailability();
  if (category === "prices") { clearRecords(); status("record-status", "Loading price sources…"); }
  if (!listing) return;
  try {
    const result = await api(`${companyPath()}/listings/${encodeURIComponent(listing)}/sources`);
    if (token !== generation || sequence !== sourcesSequence) return;
    sources = result;
    options("source", sources, "source_id", row => `${row.provider_name} / ${row.dataset_name}`);
    if (preferredSource && sources.some(row => row.source_id === preferredSource)) $("source").value = preferredSource;
    updateSourceSummary(); invalidatePreview(); updateOperationAvailability(); if (category === "prices") { offset = 0; loadRecords(); }
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
$("listing").addEventListener("change", () => { offset = 0; listingChanged(); loadSources(); });
$("source").addEventListener("change", () => { offset = 0; updateSourceSummary(); invalidatePreview(); updateOperationAvailability(); loadRecords(); });
$("filter").addEventListener("click", () => { offset = 0; loadRecords(); });
$("refresh").addEventListener("click", () => { if (company) chooseCompany(company); });
$("clear").addEventListener("click", clearDetail);
loadCompanies();

function selectedListing() { return listings.find(row => row.id === $("listing").value); }
function selectedSource() { return sources.find(row => row.source_id === $("source").value); }
function rawSource(source) {
  return source && ((source.provider_name === "alpha_vantage" && source.dataset_name === "TIME_SERIES_DAILY") ||
    (source.provider_name.startsWith("csv_") && source.dataset_name === "RAW_DAILY_CSV"));
}
function inputKey() {
  return JSON.stringify([company?.id, $("listing").value, $("source").value, $("valuation-date").value, $("share-age").value, $("price-age").value]);
}
function updateOperationAvailability() {
  const listing = selectedListing(), source = selectedSource();
  $("csv-fields").disabled = operationBusy || !listing;
  $("calculation-fields").disabled = operationBusy || !listing || listing.currency_code.toUpperCase() !== "USD" || !rawSource(source);
  $("preview-inputs").disabled = operationBusy || previewLoading;
  $("calculation-submit").disabled = operationBusy || previewLoading || previewKey !== inputKey();
}
function invalidatePreview() {
  previewKey = null; previewSequence++; previewLoading = false; $("split-confirm").checked = false;
  const listing = selectedListing();
  const message = !listing ? "Choose a listing." : listing.currency_code.toUpperCase() !== "USD" ? "SEC market-cap reconstruction currently supports USD listings only." : !rawSource(selectedSource()) ? "Choose a supported raw-price source with stored prices." : "Check eligible inputs before confirming split coverage.";
  status("preview-summary", message); updateOperationAvailability();
}
function resetResult(kind) {
  status(`${kind}-status`, ""); $(`${kind}-actions`).replaceChildren(); $(`${kind}-result`).textContent = "";
  $(`${kind}-result-box`).hidden = true;
}
function resetOperations() {
  $("csv-form").reset(); $("calculation-form").reset();
  status("file-summary", "No file selected."); resetResult("import"); resetResult("calculation"); invalidatePreview();
}
function listingChanged() {
  resetOperations(); const listing = selectedListing();
  $("csv-symbol").value = listing?.ticker || ""; $("csv-currency").value = listing?.currency_code || "";
  $("valuation-date").min = listing?.start_date || ""; $("valuation-date").max = listing?.end_date || "";
  updateOperationAvailability();
}
function setOperationBusy(value) {
  operationBusy = value;
  for (const id of ["search", "search-button", "refresh"]) $(id).disabled = value || (id === "refresh" && !company);
  document.querySelectorAll(".company").forEach(button => { button.disabled = value; });
  $("company-prev").disabled = value || companyOffset === 0; $("company-next").disabled = value || !companyMore;
  $("listing").disabled = value || listings.length === 0; $("source").disabled = value || sources.length === 0;
  updateOperationAvailability();
}
function evidenceLink(kind, artifactId) {
  if (!artifactId) return;
  const link = document.createElement("a"); link.textContent = "Download captured CSV";
  link.href = `/market-data/csv-artifacts/${encodeURIComponent(artifactId)}`; link.setAttribute("download", ""); $(`${kind}-actions`).append(link);
}
function showResult(kind, result) {
  $(`${kind}-result`).textContent = JSON.stringify(result, null, 2); $(`${kind}-result-box`).hidden = false;
}
async function postJSON(path, payload) {
  let response;
  try {
    response = await fetch(path, {method: "POST", headers: {Accept: "application/json", "Content-Type": "application/json"}, body: JSON.stringify(payload), cache: "no-store"});
  } catch (_) { throw new Error("Could not confirm the request outcome. Inspect stored archives or snapshots before retrying."); }
  let body;
  try { body = await response.json(); }
  catch (_) { throw new Error(`Could not read the response (${response.status}). Inspect stored records before retrying.`); }
  if (!response.ok) {
    const details = Array.isArray(body.detail) ? body.detail.map(item => `${(item.loc || []).filter(part => part !== "body").join(".")}: ${item.msg}`).join("; ") : body.detail;
    throw new Error(`Request rejected (${response.status}): ${typeof details === "string" ? details : "See API response for details"}`);
  }
  return body;
}
$("csv-file").addEventListener("change", () => {
  $("csv-confirm").checked = false; resetResult("import");
  const file = $("csv-file").files[0];
  status("file-summary", file ? `${file.name} · ${file.size} bytes. The complete file will be validated on import.` : "No file selected.");
});
$("csv-form").addEventListener("submit", async event => {
  event.preventDefault(); if (operationBusy) return;
  const listing = selectedListing(), file = $("csv-file").files[0];
  if (!listing || !$("csv-form").reportValidity()) return;
  resetResult("import");
  if (!file || file.size === 0 || file.size > 2000000) { status("import-status", "Choose a nonempty UTF-8 CSV no larger than 2 MB.", true); return; }
  if ($("csv-source-note").value.trim().length < 20) { status("import-status", "Explain the source and unadjusted-price evidence in at least 20 characters.", true); return; }
  const payload = {source_name: $("csv-source-name").value, source_url: $("csv-source-url").value,
    source_note: $("csv-source-note").value, symbol: listing.ticker, currency_code: listing.currency_code,
    confirm_unadjusted_prices: $("csv-confirm").checked};
  setOperationBusy(true); status("import-status", "Reading and importing CSV…");
  let result = null;
  try {
    const bytes = await file.arrayBuffer();
    try { payload.csv_text = new TextDecoder("utf-8", {fatal: true, ignoreBOM: true}).decode(bytes); }
    catch (_) { throw new Error("This file is not valid UTF-8. Save a UTF-8 copy before importing."); }
    result = await postJSON(`/market-data/listings/${encodeURIComponent(listing.id)}/daily/import-csv`, payload);
    showResult("import", result); evidenceLink("import", result.csv_artifact_id);
    status("import-status", result.created ? `Imported ${result.rows_received} rows: ${result.rows_inserted} inserted, ${result.rows_updated} updated.` : "This exact import already exists. No prices were changed.");
  } catch (error) { status("import-status", error.message, true); }
  finally { setOperationBusy(false); }
  if (result) { invalidatePreview(); await loadSources(result.source_id); if (category !== "prices") loadRecords(); }
});
async function previewInputs() {
  if (operationBusy || previewLoading) return;
  const listing = selectedListing(), source = selectedSource();
  if (!listing || listing.currency_code.toUpperCase() !== "USD" || !rawSource(source)) return;
  for (const id of ["valuation-date", "share-age", "price-age"]) if (!$(id).reportValidity()) return;
  invalidatePreview(); const sequence = previewSequence, key = inputKey(), token = generation;
  previewLoading = true; updateOperationAvailability(); status("preview-summary", "Checking eligible shares and latest stored price…");
  const valuation = $("valuation-date").value, shareAge = $("share-age").value, priceAge = Number($("price-age").value);
  try {
    const [shares, pricePage] = await Promise.all([
      api(`/filings/securities/${encodeURIComponent(listing.security_id)}/selected-shares?` + new URLSearchParams({valuation_date: valuation, max_age_days: shareAge})),
      api(`${companyPath()}/listings/${encodeURIComponent(listing.id)}/prices?` + new URLSearchParams({source_id: source.source_id, end: valuation, limit: 1, offset: 0}))
    ]);
    if (sequence !== previewSequence || token !== generation || key !== inputKey()) return;
    const price = pricePage.items[0];
    if (!price) throw new Error("No price is stored on or before this valuation date for the selected source.");
    const age = Math.round((Date.parse(valuation + "T00:00:00Z") - Date.parse(price.trading_date + "T00:00:00Z")) / 86400000);
    if (age > priceAge) throw new Error(`Selected price is ${age} days old; the maximum is ${priceAge}.`);
    const interval = [shares.observation_date, price.trading_date].sort();
    status("preview-summary", `Shares: ${shares.shares_outstanding} observed ${shares.observation_date}, known ${shares.known_date}. Price: ${price.close_price} USD on ${price.trading_date}. Check split coverage from ${interval[0]} through ${interval[1]}. The server revalidates inputs when saving.`);
    previewKey = key;
  } catch (error) { if (sequence === previewSequence && token === generation) status("preview-summary", error.message, true); }
  finally { if (sequence === previewSequence) { previewLoading = false; updateOperationAvailability(); } }
}
$("preview-inputs").addEventListener("click", previewInputs);
for (const id of ["valuation-date", "share-age", "price-age"]) $(id).addEventListener("input", invalidatePreview);
$("calculation-form").addEventListener("submit", async event => {
  event.preventDefault(); if (operationBusy) return;
  if (!previewKey || previewKey !== inputKey()) { invalidatePreview(); return; }
  if (!$("calculation-form").reportValidity()) return;
  resetResult("calculation");
  if ($("split-note").value.trim().length < 20) { status("calculation-status", "Explain the split-coverage evidence in at least 20 characters.", true); return; }
  const listing = selectedListing(), source = selectedSource();
  const payload = {valuation_date: $("valuation-date").value, price_source_id: source.source_id,
    max_share_age_days: Number($("share-age").value), max_price_age_days: Number($("price-age").value),
    confirm_split_coverage: $("split-confirm").checked, split_evidence_url: $("split-url").value, split_evidence_note: $("split-note").value};
  setOperationBusy(true); status("calculation-status", "Saving captured market-cap calculation…");
  let result = null;
  try {
    result = await postJSON(`/market-cap/listings/${encodeURIComponent(listing.id)}/reconstruct-sec`, payload);
    showResult("calculation", result); evidenceLink("calculation", result.manifest.price.csv_artifact_id);
    status("calculation-status", `${result.created ? "Saved new snapshot" : "Identical snapshot already exists"}: ${result.manifest.result.market_cap_usd} USD on ${result.valuation_date}.`);
    const button = document.createElement("button"); button.type = "button"; button.textContent = "Inspect saved snapshot";
    const companyId = company.id;
    button.addEventListener("click", () => { if (company?.id === companyId) inspect({id: result.snapshot_id}, "snapshots", companyId); });
    $("calculation-actions").append(button);
  } catch (error) { status("calculation-status", error.message, true); }
  finally { setOperationBusy(false); }
  if (result) loadRecords();
});
updateOperationAvailability();
