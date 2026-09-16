"use strict";
/* ================================================ families browse
   The default tier is the families with motif data: the only set the site can
   show gene-level data for. */
const famState = {
  filters: { q: "", tier: "motif", class: "", mibig: false, sort: "bgcs", dir: "" },
  page: 1, perPage: 50, total: 0, rows: [], searchTimer: null, seq: 0, facets: null,
  widenedFor: null, widenNote: "",
};
const FAM_PER_PAGE = [50, 100, 200];   // the API caps limit at 200
const famTierLabel = t => (FAM_TIERS.find(([v]) => v === t) || [, t])[1];
const FAM_TIERS = [["motif", "motif data"], ["cog", "COG data"],
                   ["tf", "TF annotation"], ["all", "all families"]];
const FAM_CLASSES = ["NRP", "Polyketide", "Other", "Terpene", "RiPP", "Saccharide", "Alkaloid"];

/* key, heading, cell class, tooltip. A key that is also an API `sort` value
   makes the heading clickable; "" leaves it inert. MIBiG has no cheap
   server-side ordering, so its heading stays inert. */
const FAM_COLS = [
  ["id",      "family",  "",    "BiG-FAM family identifier"],
  ["bgcs",    "N BGCs",  "n",   "BGCs assigned to this family"],
  ["class",   "class",   "",    "dominant product class(es), a set not a ranking"],
  ["species", "N species", "n", "distinct species across the family's BGCs"],
  ["tf",      "TFs",     "tfc", "most common TF family across this family's orthologous groups"],
  ["",        "MIBiG",   "",    "MIBiG reference clusters in this family; characterised BGCs, and searching the accession comes back here"],
  ["data",    "data",    "",    "which gene-level data this family carries"],
];
/* must mirror FAM_DIR in app/routers/families.py: names and ids read
   low-to-high, counts high-to-low */
const FAM_DIR0 = { id: "asc", class: "asc", tf: "asc" };
const famDir = k => famState.filters.dir || FAM_DIR0[k] || "desc";

async function familiesPage(params, my) {
  const fl = famState.filters;
  if (params) {                                   // the hash is the source of truth
    // a real navigation clears the widen notice; the auto-widen redraw passes
    // params === null and keeps its own
    famState.widenNote = ""; famState.widenedFor = null;
    fl.q        = params.get("q") || "";
    fl.tier     = FAM_TIERS.some(([v]) => v === params.get("tier")) ? params.get("tier") : "motif";
    fl.class    = FAM_CLASSES.includes(params.get("class")) ? params.get("class") : "";
    fl.mibig    = params.get("mibig") === "1";
    fl.sort     = FAM_COLS.some(([v]) => v === params.get("sort")) ? params.get("sort") : "bgcs";
    fl.dir      = ["asc", "desc"].includes(params.get("dir")) ? params.get("dir") : "";
    famState.perPage = FAM_PER_PAGE.includes(+params.get("n")) ? +params.get("n") : 50;
    famState.page    = Math.max(1, parseInt(params.get("page"), 10) || 1);
  }
  famState.rows = [];
  if (!famState.facets) famState.facets = await api("families/facets").catch(() => null);
  if (stale(my)) return;
  const fc = famState.facets;
  const cls = fc && fc[fl.tier] ? fc[fl.tier].classes : null;

  $("#main").innerHTML = `
    <h2>Gene cluster families</h2>
    <p class="muted" style="max-width:76ch">Every BiG-FAM family in the collection.
      Search by family (<span class="seq">FAM2526</span>), by MIBiG accession
      (<span class="seq">BGC0001286</span>), by assembly accession
      (<span class="seq">GCF_000203835</span>), or by genus, species or phylum. The
      counts are exact, not sampled. Most families carry no
      gene-level data; the default view is the ${fc ? fmt(fc.motif.n) : ""} with predicted
      motifs. Click any column heading to sort by it.</p>
    <div class="filters">
      <input id="famq" type="search" autocomplete="off" value="${esc(fl.q)}"
        placeholder="FAM2526, BGC0001286, GCF_000203835, genus, species, phylum"
        oninput="famSearch(this.value)">
      <label>show
        <select onchange="famFilter('tier', this.value)">
          ${FAM_TIERS.map(([v, t]) => `<option value="${v}" ${fl.tier === v ? "selected" : ""}
            >${t}${fc ? " (" + fmt(fc[v].n) + ")" : ""}</option>`).join("")}
        </select></label>
      <label>class
        <select onchange="famFilter('class', this.value)">
          <option value="">any</option>
          ${FAM_CLASSES.map(v => `<option value="${v}" ${fl.class === v ? "selected" : ""}
            ${cls && !cls[v] && fl.class !== v ? "disabled" : ""}
            >${v}${cls ? " (" + fmt(cls[v]) + ")" : ""}</option>`).join("")}
        </select></label>
      <label title="only families holding at least one MIBiG reference cluster, a BGC with a characterised product">
        <input type="checkbox" ${fl.mibig ? "checked" : ""}
          onchange="famFilter('mibig', this.checked)">
        has MIBiG${fc ? " (" + fmt(fc[fl.tier].n_mibig) + ")" : ""}</label>
      <span id="famcount" class="muted"></span>
    </div>
    <div id="famtable"></div>
    <div id="fampager" class="pager" hidden></div>`;
  loadFamilies();
}

function famFilter(k, v) {
  famState.widenNote = "";
  famState.filters[k] = v;
  famState.page = 1; famState.rows = [];
  famSyncHash();
  // the tier's class and MIBiG counts change, so redraw the controls too
  if (k === "tier") return familiesPage(null, routeId);
  loadFamilies();
}

function famSort(k) {
  const fl = famState.filters;
  fl.dir  = fl.sort === k ? (famDir(k) === "asc" ? "desc" : "asc") : (FAM_DIR0[k] || "desc");
  fl.sort = k;
  famState.page = 1; famState.rows = [];
  famSyncHash();
  loadFamilies();
}

function famGo(pg) {
  famState.page = pg;
  famSyncHash();
  loadFamilies();
  window.scrollTo(0, 0);
}

function famPerPage(v) {
  famState.perPage = FAM_PER_PAGE.includes(+v) ? +v : 50;
  famState.page = 1;
  famSyncHash();
  loadFamilies();
}

function famSearch(v) {
  famState.widenNote = "";
  clearTimeout(famState.searchTimer);
  famState.searchTimer = setTimeout(() => famFilter("q", v.trim()), 220);
}

/* replaceState, never location.hash: assigning the hash re-enters route(),
   which rebuilds #main and destroys the input's caret on every keystroke. */
function famSyncHash() {
  const fl = famState.filters, p = new URLSearchParams();
  if (fl.q) p.set("q", fl.q);
  if (fl.tier !== "motif") p.set("tier", fl.tier);
  if (fl.class) p.set("class", fl.class);
  if (fl.mibig) p.set("mibig", "1");
  if (fl.sort !== "bgcs") p.set("sort", fl.sort);
  if (fl.dir && fl.dir !== (FAM_DIR0[fl.sort] || "desc")) p.set("dir", fl.dir);
  if (famState.page > 1) p.set("page", famState.page);
  if (famState.perPage !== 50) p.set("n", famState.perPage);
  const s = p.toString();
  history.replaceState(null, "", "#families" + (s ? "?" + s : ""));
}

/* The row navigates to the family, so the link must stop the click reaching it. */
const mibigLink = a => `<a class="badge mibig" href="${MIBIG_URL}${esc(a)}" target="_blank"
  rel="noopener" onclick="event.stopPropagation()" title="open ${esc(a)} in MIBiG">${esc(a)}</a>`;

function mibigCell(f) {
  const accs = f.mibig;
  if (!accs || !accs.length) return '<span class="muted">–</span>';
  if (accs.length === 1) return mibigLink(accs[0]);
  return `<span class="mibigs" data-fam="${esc(f.family_id)}">${mibigLink(accs[0])
    }<span class="more" onclick="event.stopPropagation();mibigToggle(this)"
      title="show the other ${accs.length - 1}">+${accs.length - 1}</span></span>`;
}

/* Extra accessions open on demand, so a long list does not set the column
   width for every row. */
function mibigToggle(el) {
  const wrap = el.closest(".mibigs");
  const row = famState.rows.find(r => r.family_id === wrap.dataset.fam);
  if (!row) return;
  const open = wrap.dataset.open === "1";
  wrap.dataset.open = open ? "" : "1";
  wrap.innerHTML = open
    ? mibigLink(row.mibig[0]) + `<span class="more" onclick="event.stopPropagation();mibigToggle(this)"
        title="show the other ${row.mibig.length - 1}">+${row.mibig.length - 1}</span>`
    : row.mibig.map(mibigLink).join("") + `<span class="more"
        onclick="event.stopPropagation();mibigToggle(this)" title="collapse">less</span>`;
}

/* the API caps offset at 200,000: a deeper ?page= clamps here instead of
   returning a 422 */
const FAM_MAX_OFFSET = 200000;

async function loadFamilies() {
  const fl = famState.filters, my = ++famState.seq;
  famState.page = Math.max(1, Math.min(famState.page,
    Math.floor(FAM_MAX_OFFSET / famState.perPage) + 1));
  const qs = new URLSearchParams({ tier: fl.tier, sort: fl.sort, dir: famDir(fl.sort),
                                   offset: (famState.page - 1) * famState.perPage,
                                   limit: famState.perPage });
  if (fl.q) qs.set("q", fl.q);
  if (fl.class) qs.set("class", fl.class);
  if (fl.mibig) qs.set("mibig", "1");
  let d;
  try { d = await api("families?" + qs); }
  catch (r) {
    if (my !== famState.seq || !$("#famtable")) return;
    // a 422 from the prefix cap carries a sentence in `detail`; a validation
    // 422 carries a list, which is not shown
    const why = await (r && r.json
      ? r.json().then(j => typeof j.detail === "string" ? j.detail : null).catch(() => null)
      : null);
    $("#famtable").innerHTML = `<p class="muted">${esc(why) || "Could not load families."}</p>`;
    $("#fampager").hidden = true;
    return;
  }
  // two requests are routinely in flight and can resolve out of order
  if (my !== famState.seq || !$("#famtable")) return;

  /* An exact identifier can sit outside the default tier, so widen to every
     family once and say so. Keyed on the query: at most once per search, and
     never fighting a tier the user picks afterwards. */
  const key = [fl.q, fl.class, fl.mibig].join("|");
  if (famState.page === 1 && d.total === 0 && d.total_all > 0 && fl.tier !== "all"
      && famState.widenedFor !== key) {
    famState.widenedFor = key;
    famState.widenNote = `Nothing in <b>${esc(famTierLabel(fl.tier))}</b> matches${
      fl.q ? " " + esc(fl.q) : ""}, so this is every family.`;
    fl.tier = "all";
    famState.page = 1; famState.rows = [];
    famSyncHash();
    return familiesPage(null, routeId);
  }

  // a stale ?page= beyond the last page of this result set: clamp and refetch
  const last = Math.max(1, Math.ceil(d.total / famState.perPage));
  if (!d.families.length && d.total > 0 && famState.page > last) {
    famState.page = last;
    famSyncHash();
    return loadFamilies();
  }

  famState.total = d.total;
  famState.rows = d.families;
  $("#famcount").textContent = `${fmt(d.total)} famil${d.total === 1 ? "y" : "ies"}`;
  if (!famState.rows.length) {
    $("#famtable").innerHTML = `<p class="muted">No families match${
      fl.q ? " <b>" + esc(fl.q) + "</b>" : ""}${
      fl.class ? " in " + esc(fl.class) : ""}${
      fl.mibig ? " with a MIBiG accession" : ""}${
      d.total_all ? ` in <b>${esc(famTierLabel(fl.tier))}</b>, but <span class="navlink"
        style="padding:0" onclick="famFilter('tier','all')">${fmt(d.total_all)} across all
        families</span>` : " anywhere in the collection"}.</p>`;
    $("#fampager").hidden = true;
    return;
  }
  const head = FAM_COLS.map(([k, label, cls, tip]) => {
    const on = k && fl.sort === k;
    if (!k) return `<th title="${esc(tip)}">${label}</th>`;
    return `<th class="${cls === "n" ? "n " : ""}srt${on ? " on" : ""}" title="${esc(tip)}"
      onclick="famSort('${k}')">${label}<span class="ar">${
        on ? (famDir(k) === "asc" ? "▲" : "▼") : ""}</span></th>`;
  }).join("");
  $("#famtable").innerHTML = `${famState.widenNote
      ? `<p class="widen">${famState.widenNote}</p>` : ""}<table class="grid">
    <tr>${head}</tr>
    ${famState.rows.map(f => `
      <tr class="clk" onclick="go('family/${esc(f.family_id)}')">
        <td><b>${esc(f.family_id)}</b></td>
        <td class="n">${fmt(f.n_bgcs)}</td>
        <td class="muted">${esc(f.dominant_class || "–")}</td>
        <td class="n">${fmt(f.n_species)}</td>
        <td class="tfc" title="${esc(f.dominant_tf || "")}">${
          f.dominant_tf ? esc(f.dominant_tf) : '<span class="muted">–</span>'}</td>
        <td style="white-space:nowrap">${mibigCell(f)}</td>
        <td style="white-space:nowrap">${
          [[f.has_motif_data, "motifs"], [f.has_cog_data, "COGs"], [f.has_tf_data, "TF"]]
            .filter(([on]) => on).map(([, t]) => `<span class="badge">${t}</span>`).join("")
          || '<span class="muted">–</span>'}</td>
      </tr>`).join("")}</table>`;
  famPager();
}

function famPager() {
  const el = $("#fampager");
  if (!el) return;
  const per = famState.perPage, cur = famState.page;
  const pages = Math.max(1, Math.ceil(famState.total / per));
  el.hidden = pages <= 1 && per === 50;
  if (el.hidden) { el.innerHTML = ""; return; }
  const want = new Set([1, pages]);
  for (let p = cur - 2; p <= cur + 2; p++) if (p >= 1 && p <= pages) want.add(p);
  const seq = [...want].sort((a, b) => a - b);
  let nums = "", prev = 0;
  for (const p of seq) {
    if (p - prev > 1) nums += '<span class="gap">…</span>';
    nums += p === cur
      ? `<button class="on">${fmt(p)}</button>`
      : `<button onclick="famGo(${p})">${fmt(p)}</button>`;
    prev = p;
  }
  el.innerHTML = `
    <button ${cur === 1 ? "disabled" : `onclick="famGo(${cur - 1})"`}>‹</button>
    ${nums}
    <button ${cur === pages ? "disabled" : `onclick="famGo(${cur + 1})"`}>›</button>
    <span class="muted" style="margin-left:6px">page ${fmt(cur)} of ${fmt(pages)}</span>
    <label class="per">per page
      <select onchange="famPerPage(this.value)">
        ${FAM_PER_PAGE.map(n => `<option value="${n}" ${per === n ? "selected" : ""}>${n}</option>`).join("")}
      </select></label>`;
}
