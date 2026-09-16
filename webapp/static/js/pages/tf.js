"use strict";
/* ================================================ Path B: TF / SSN clusters
   Cross-family view over the TF families with an SSN. Coverage is sparse, so
   every list here needs an empty state. */
const tfState = { tf: null, filters: { min_nodes: 5, has_motifs: false, has_prodoric: false,
                                       sort: "nodes", q: "" }, offset: 0, total: 0, rows: [],
                  ssn: null, mcOffset: 0, mcTotal: 0, searchTimer: null,
                  prodoric: null, proq: "", seq: 0 };

const qv = q => q == null ? "–" : (+q < 0.001 ? (+q).toExponential(1) : (+q).toFixed(4));
const pct = f => f == null ? "–" : Math.round(f * 100) + "%";
const covBar = f => `<span class="bar" style="display:inline-block;width:56px;vertical-align:middle">
    <i style="width:${Math.round((f || 0) * 100)}%"></i></span>`;
/* Clusters are addressed by TF family + 0-based MCL cluster number, as in the
   pipeline files. ssn_id is a build-time surrogate: never show it. */
const ssnHref = (tf, mcl) => `ssn/${encodeURIComponent(tf)}/${mcl}`;
const ssnName = (tf, mcl) => `${tf} cluster ${mcl}`;

/* Only real MX###### accessions have a page at prodoric.de; a custom id such
   as MX_EctR1 renders as text. */
const prodoricLink = acc => acc && /^MX\d+$/.test(acc)
  ? `<a href="https://www.prodoric.de/matrix/${encodeURIComponent(acc)}.html"
        target="_blank" rel="noopener" class="ext" onclick="event.stopPropagation()"
        title="open ${esc(acc)} at prodoric.de">${esc(acc)}</a>`
  : acc ? esc(acc) : '<span class="muted">–</span>';

async function tfHome(my) {
  $("#main").innerHTML = '<div class="spin">Loading regulators…</div>';
  const [d, v] = await Promise.all([api("tf/families"),
                                   api("prodoric/validation")]);
  if (stale(my)) return;
  const cards = d.tf_families.map(f => `
    <div class="card" onclick="go('tf/${f.tf_family_id}')">
      <h3>${esc(f.name)}</h3>
      <div class="muted" style="font-size:14px">${fmt(f.n_nodes)} regulator proteins
        from ${fmt(f.n_families)} gene cluster families</div>
      <div class="num">
        <div><b>${fmt(f.n_ssn)}</b><span>sequence clusters</span></div>
        <div><b>${fmt(f.n_ssn_with_motifs)}</b><span>with motif clusters</span></div>
        <div><b>${fmt(f.n_validated)}</b><span>matched a known site</span></div>
      </div>
    </div>`).join("");

  tfState.prodoric = v;
  $("#main").innerHTML = `
    <h2>Transcription-factor regulators across families</h2>
    <p class="muted" style="max-width:70ch">Regulator proteins from every gene cluster
      family are clustered by sequence similarity (SSN). Motifs found independently in
      different families then group into <b>motif clusters</b> inside each SSN cluster.
      Evidence that the same regulatory signal recurs across different BGC families.</p>
    <div class="cards">${cards}</div>
    <div class="sec">Known regulators</div>
    <p class="muted" style="max-width:80ch;margin:2px 0 10px;font-size:14px">
      Each cluster's motifs are compared to the regulator's known binding site with
      Tomtom; a motif counts as a match at <b>q ≤ ${v.q_match ?? 0.1}</b>.
      <b>NA</b> means there is no q-value to report. Nothing matched, the cluster had no
      motifs to test, or the regulator is a singleton with no cluster at all.</p>
    <div class="filters">
      <input id="proq" type="search" autocomplete="off"
        placeholder="regulator, organism, PRODORIC ID…"
        oninput="proSearch(this.value)">
      <span id="procount" class="muted"></span>
    </div>
    <div id="protable"></div>`;
  tfState.proq = "";
  renderProdoric();
}

const PRO_STATUS = {
  matched:     ["matched",            "#047857", "a motif cluster matches the known site"],
  no_match:    ["no match",           "",        "motifs were tested against it, none matched"],
  not_tested:  ["nothing to test",    "",        "in an SSN cluster, but it had no motifs to test"],
  singleton:   ["singleton",          "",        "in the SSN but paired with nothing, so no cluster"],
  /* only returned for scope=all, which the page never requests; kept so an
     unexpected status renders instead of throwing */
  not_in_ssn:  ["not in an SSN",     "",        "no sequence-similarity network for its TF family"],
};

/* Filtered in memory. Only #protable is rewritten, so the input keeps its
   focus and caret. */
function proSearch(q) { tfState.proq = q.trim().toLowerCase(); renderProdoric(); }

function proMatch(x, q) {
  if (!q) return true;
  return [x.tf_name, x.organism, x.mx_acc, x.tf_family,
          PRO_STATUS[x.status][0],
          x.mcl_cluster != null ? "cluster " + x.mcl_cluster : ""]
    .some(f => (f || "").toString().toLowerCase().includes(q));
}

function renderProdoric() {
  const v = tfState.prodoric, q = tfState.proq;
  const list = v.validation.filter(x => proMatch(x, q));
  const na = '<span class="muted">NA</span>';
  if ($("#procount")) $("#procount").textContent = q
    ? `${list.length} of ${v.validation.length} regulators`
    : `${v.validation.length} regulators`;
  if (!list.length) {
    $("#protable").innerHTML = `<p class="muted">No regulator matches “${esc(q)}”.</p>`;
    return;
  }
  $("#protable").innerHTML = `<table class="grid">
    <tr><th>TF</th><th>organism</th><th>PRODORIC</th><th>family</th>
        <th title="the SSN cluster this TF falls in">cluster</th>
        <th>known consensus</th>
        <th class="n" title="Tomtom q-value of the best matching motif">best q-value</th>
        <th>status</th></tr>
    ${list.map(x => {
      const [label, colour, tip] = PRO_STATUS[x.status];
      const inCluster = x.mcl_cluster != null;
      return `<tr${inCluster ? ` class="clk" onclick="go('${ssnHref(x.tf_family, x.mcl_cluster)}')"` : ""}>
        <td><b>${esc(x.tf_name || x.mx_acc)}</b></td>
        <td class="muted"><i>${esc(x.organism || "")}</i></td>
        <td>${prodoricLink(x.mx_acc)}</td>
        <td>${x.tf_family ? esc(x.tf_family) : na}</td>
        <td style="white-space:nowrap">${inCluster ? "cluster " + x.mcl_cluster : na}</td>
        <td class="seq">${x.consensus ? esc(x.consensus) : na}</td>
        <td class="n">${x.status === "matched"
          ? `<b style="color:#047857">${qv(x.best_qvalue)}</b>` : na}</td>
        <td style="white-space:nowrap"><span class="badge${colour ? "" : " off"}" title="${esc(tip)}"
          ${colour ? `style="background:#ecfdf5;color:${colour}"` : ""}>${label}</span></td>
      </tr>`;
    }).join("")}</table>`;
}
