"use strict";
/* ------------------------------------------------ SSN cluster list */
async function ssnListPage(tfId, my) {
  tfState.tf = tfId; tfState.offset = 0; tfState.rows = []; tfState.filters.q = "";
  const d = await api("tf/families");
  if (stale(my)) return;
  const f = d.tf_families.find(x => x.tf_family_id === tfId);
  const fl = tfState.filters;
  $("#main").innerHTML = `
    <div class="crumb"><a onclick="go('tf')">Regulators</a> › ${esc(f ? f.name : tfId)}</div>
    <h2>${esc(f ? f.name : "TF family")} sequence clusters</h2>
    <div class="muted">${f ? fmt(f.n_ssn) + " clusters · " + fmt(f.n_nodes) + " proteins · "
      + fmt(f.n_ssn_with_motifs) + " clusters with motif data" : ""}</div>
    <div class="filters">
      <input id="ssnq" type="search" autocomplete="off" value="${esc(fl.q)}"
        placeholder="Cluster no., known regulator, phylum"
        oninput="ssnSearch(this.value)">
      <label><input type="checkbox" id="f-mot" ${fl.has_motifs ? "checked" : ""}
        onchange="setFilter('has_motifs', this.checked)"> has motif clusters</label>
      <label><input type="checkbox" id="f-pro" ${fl.has_prodoric ? "checked" : ""}
        onchange="setFilter('has_prodoric', this.checked)"> contains a known regulator</label>
      <label>min proteins
        <select onchange="setFilter('min_nodes', +this.value)">
          ${[1, 5, 20, 50, 100].map(n =>
            `<option value="${n}" ${fl.min_nodes === n ? "selected" : ""}>${n}</option>`).join("")}
        </select></label>
      <label>sort by
        <select onchange="setFilter('sort', this.value)">
          ${[["nodes", "proteins"], ["families", "families"], ["motifs", "motif clusters"],
             ["prodoric", "known regulators"]].map(([v, t]) =>
            `<option value="${v}" ${fl.sort === v ? "selected" : ""}>${t}</option>`).join("")}
        </select></label>
      <span id="ssncount" class="muted"></span>
    </div>
    <div id="ssntable"></div>
    <button id="ssn-more" class="loadmore" hidden onclick="loadSSNs()">Load more clusters</button>`;
  loadSSNs();
}

function setFilter(k, v) { tfState.filters[k] = v; tfState.offset = 0; tfState.rows = []; loadSSNs(); }

function ssnSearch(v) {
  clearTimeout(tfState.searchTimer);
  tfState.searchTimer = setTimeout(() => setFilter("q", v.trim()), 220);
}

async function loadSSNs() {
  const fl = tfState.filters, my = ++tfState.seq;
  const qs = new URLSearchParams({ tf_family_id: tfState.tf, min_nodes: fl.min_nodes,
    sort: fl.sort, offset: tfState.offset, limit: 50 });
  if (fl.has_motifs) qs.set("has_motifs", "true");
  if (fl.has_prodoric) qs.set("has_prodoric", "true");
  if (fl.q) qs.set("q", fl.q);
  const d = await api("ssn?" + qs);
  if (my !== tfState.seq || !$("#ssntable")) return;   // superseded or page gone
  tfState.total = d.total;
  tfState.rows = tfState.rows.concat(d.clusters);
  tfState.offset += d.clusters.length;
  $("#ssncount").textContent = `${fmt(d.total)} cluster${d.total === 1 ? "" : "s"}`;
  if (!tfState.rows.length) {
    $("#ssntable").innerHTML = `<p class="muted">No clusters match${
      fl.q ? " <b>" + esc(fl.q) + "</b>" : ""}. Try clearing a filter${
      fl.min_nodes > 1 ? " or lowering the minimum protein count" : ""}.</p>`;
    $("#ssn-more").hidden = true;
    return;
  }
  $("#ssntable").innerHTML = `<table class="grid">
    <tr><th title="the TF family's own MCL cluster number, as used by the pipeline">cluster</th><th class="n">proteins</th><th class="n">families</th>
        <th class="n" title="groups of motifs recurring across families in this cluster">motif clusters</th>
        <th title="the cluster's most widespread motif cluster: the share of families with pipeline data that contributed a motif to it">best coverage</th>
        <th title="PRODORIC transcription factors sitting in this cluster">known regulators</th>
        <th>phyla</th></tr>
    ${tfState.rows.map(c => `
      <tr class="clk" onclick="go('${ssnHref(c.tf_family, c.mcl_cluster)}')">
        <td><b>cluster ${c.mcl_cluster}</b></td>
        <td class="n">${fmt(c.n_nodes)}</td>
        <td class="n">${fmt(c.n_families)}</td>
        <td class="n">${c.n_motif_clusters ? fmt(c.n_motif_clusters) : '<span class="muted">–</span>'}</td>
        <td>${c.best_coverage != null ? covBar(c.best_coverage) + " " + pct(c.best_coverage)
                                      : '<span class="muted">–</span>'}</td>
        <td>${c.prodoric_tfs.length ? c.prodoric_tfs.map(t =>
              `<span class="badge">${esc(t)}</span>`).join("") : '<span class="muted">–</span>'}</td>
        <td class="muted">${esc(c.top_phyla.slice(0, 2).join(", "))}</td>
      </tr>`).join("")}</table>`;
  $("#ssn-more").hidden = tfState.offset >= d.total;
}

/* ------------------------------------------------ SSN cluster detail */
/* a bare #ssn/{ssn_id} carries the surrogate: resolve it and rewrite the hash in place */
async function ssnRedirect(ssnId, my) {
  $("#main").innerHTML = '<div class="spin">Loading cluster…</div>';
  try {
    const d = await api("ssn/" + ssnId);
    /* stale check before location.replace(): a lookup finishing after the user
       has navigated away would otherwise drag them back here */
    if (stale(my)) return;
    location.replace("#" + ssnHref(d.cluster.tf_family, d.cluster.mcl_cluster));
  } catch { if (!stale(my)) $("#main").innerHTML = "<p>Cluster not found.</p>"; }
}

async function ssnPage(tf, mcl, my) {
  $("#main").innerHTML = '<div class="spin">Loading cluster…</div>';
  let d;
  try { d = await api(`ssn/by/${encodeURIComponent(tf)}/${mcl}`); }
  catch { if (!stale(my)) $("#main").innerHTML = "<p>Cluster not found.</p>"; return; }
  if (stale(my)) return;
  const c = d.cluster;
  tfState.ssn = c.ssn_id; tfState.mcTotal = d.n_motif_clusters;
  tfState.mcOffset = d.motif_clusters.length;

  // `matched` is decided server-side at Q_MATCH, the same rule as the
  // regulators table -- never re-derive it from n_motifs_matched here
  const val = d.validation.filter(v => v.matched).map(v => `
    <div class="valid">
      <b>${esc(v.tf_name || v.mx_acc)}</b> <span class="muted"><i>${esc(v.organism || "")}</i></span>
      de-novo motifs match the known binding site
      (<b class="q">q = ${qv(v.best_qvalue)}</b>, ${v.n_motifs_matched} of
      ${fmt(v.n_motifs_tested)} motifs across ${fmt(v.n_motif_clusters_tested)} clusters).
      <div class="muted" style="margin-top:4px">PRODORIC consensus
        <span class="seq">${esc(v.consensus || "?")}</span>
        · best match <span class="seq">${esc(v.best_query_motif || "")}</span>
        ${v.mc_id ? `· <a style="cursor:pointer;color:var(--accent)"
            onclick="mcPanel(${v.mc_id})">view motif cluster ${v.mc_id}</a>` : ""}</div>
    </div>`).join("");
  const tested = d.validation.filter(v => !v.matched);

  $("#main").innerHTML = `
    <div class="crumb"><a onclick="go('tf')">Regulators</a> ›
      <a onclick="go('tf/${c.tf_family_id}')">${esc(c.tf_family || "")}</a> ›
      cluster ${c.mcl_cluster}</div>
    <h2>${esc(ssnName(c.tf_family || "TF", c.mcl_cluster))}</h2>
    <div class="muted">${fmt(c.n_nodes)} regulator proteins ·
      ${fmt(c.n_families)} gene cluster families ·
      ${fmt(d.n_member_families_with_motifs)} of them with motif data</div>
    <div style="margin-top:8px">
      ${c.bgc_classes.map(x => `<span class="badge">${esc(x)}</span>`).join("")}
      ${c.top_phyla.map(x => `<span class="badge off">${esc(x)}</span>`).join("")}
    </div>
    ${c.rep_aa_seq ? `
    <div class="repseq">
      <span class="muted">representative protein</span>
      <b>${esc(c.rep_locus_tag || "")}</b>
      <span class="muted">${fmt(c.rep_aa_seq.length)} aa</span>
      <span class="navlink" style="padding:0" onclick="repToggle(this)">show sequence</span>
      <button class="copybtn" onclick="repCopy(this)" title="copy as FASTA">copy</button>
      <pre hidden data-lt="${esc(c.rep_locus_tag || "rep")}">${esc(c.rep_aa_seq)}</pre>
    </div>` : ""}
    ${val}
    ${!val && d.prodoric_anchors.length ? `<p class="muted" style="margin-top:12px">
       Contains known regulator${d.prodoric_anchors.length > 1 ? "s" : ""}
       ${d.prodoric_anchors.map(a => `<b>${esc(a.tf_name || a.mx_acc)}</b>
         (<i>${esc(a.organism || "")}</i>, site <span class="seq">${esc(a.consensus || "?")}</span>)`).join(", ")}
       ${tested.length ? ", and no motif cluster matched its binding site." : "."}</p>` : ""}

    <div class="sec">Motif clusters
      <span class="muted" style="font-weight:400">${d.n_motif_clusters
        ? "(" + fmt(d.n_motif_clusters) + " groups of motifs recurring across "
          + "families; coverage ≥ 0.5 = conserved)"
        : ""}</span></div>
    <div id="mcgrid" class="mcgrid"></div>
    <button id="mcmore" hidden onclick="loadMoreMC()">Load more motif clusters</button>

    <div class="sec">Contributing families</div>
    <div id="famtable"></div>`;

  renderMC(d.motif_clusters, true);
  $("#famtable").innerHTML = d.top_families.length ? `<table class="grid">
      <tr><th>family</th><th class="n">proteins in cluster</th><th class="n">BGCs</th>
          <th>dominant class</th><th>motif data</th></tr>
      ${d.top_families.map(f => `
        <tr class="clk" onclick="go('family/${esc(f.family_id)}')">
          <td><b>${esc(f.family_id)}</b></td>
          <td class="n">${f.n_nodes}</td>
          <td class="n">${fmt(f.n_bgcs)}</td>
          <td>${esc(f.dominant_class || "–")}</td>
          <td>${f.has_motif_data ? '<span class="badge">yes</span>'
                                 : '<span class="badge off">no</span>'}</td>
        </tr>`).join("")}</table>`
    : '<p class="muted">No member families recorded.</p>';
}

/* The sequence stays in the <pre>, never in an attribute. Copied as FASTA. */
function repToggle(el) {
  const pre = el.closest(".repseq").querySelector("pre");
  pre.hidden = !pre.hidden;
  el.textContent = pre.hidden ? "show sequence" : "hide sequence";
}

function repCopy(btn) {
  const el = btn.closest(".repseq").querySelector("pre");
  const fasta = ">" + el.dataset.lt + "\n" + el.textContent;
  const done = ok => { btn.textContent = ok ? "copied" : "copy failed";
                       setTimeout(() => { btn.textContent = "copy"; }, 1400); };
  if (navigator.clipboard && navigator.clipboard.writeText)
    navigator.clipboard.writeText(fasta).then(() => done(true), () => done(false));
  else done(false);
}

/* the paper's threshold: a motif cluster recovered in >=50% of the SSN
   cluster's families with motif data counts as conserved */
const CONSERVED_BADGE = '<span class="badge" style="background:#ecfdf5;color:#047857" ' +
  'title="recovered in at least half of the cluster&#39;s families with motif data ' +
  '— the paper&#39;s conserved threshold">conserved</span>';

function renderMC(list, reset) {
  const g = $("#mcgrid");
  if (reset) g.innerHTML = "";
  if (!list.length && reset) {
    g.innerHTML = '<p class="muted">No motif clusters in this SSN cluster. The regulators '
                + 'group by sequence, but no shared upstream motif was recovered.</p>';
  }
  g.insertAdjacentHTML("beforeend", list.map(m => `
    <div class="mccard" onclick="mcPanel(${m.mc_id})">
      <div class="top">
        <b>cluster ${m.mc_id}</b>
        ${m.family_coverage >= 0.5 ? CONSERVED_BADGE : ""}
        ${m.is_best_for_ssn ? '<span class="badge">best in cluster</span>' : ""}
      </div>
      ${m.pwm_parsed ? logoSVG(m.pwm_parsed.matrix) : ""}
      <div class="meta">
        <span>${fmt(m.n_motifs)} motifs</span>
        <span>${fmt(m.n_cogs)} COGs</span>
        <span>${m.n_families_motif}/${m.n_families_ssn} families</span>
        ${covBar(m.family_coverage)}<span>${pct(m.family_coverage)}</span>
      </div>
    </div>`).join(""));
  $("#mcmore").hidden = tfState.mcOffset >= tfState.mcTotal;
}

async function loadMoreMC() {
  const d = await api(`ssn/${tfState.ssn}/motif-clusters?offset=${tfState.mcOffset}&limit=24`);
  tfState.mcOffset += d.motif_clusters.length;
  tfState.mcTotal = d.total;
  renderMC(d.motif_clusters, false);
}
