"use strict";
/* ------------------------------------------------ gene click -> side panel */
async function geneClick(e) {
  $("#tooltip").style.display = "none";
  const d = JSON.parse(e.target.dataset.cds);
  if (d.cog != null && !state.selected.has(d.cog)) { state.selected.add(d.cog); renderChips(); repaint(); }
  const p = $("#panel");
  p.innerHTML = `<button class="close" onclick="this.parentNode.classList.remove('open')">×</button>
    <h3>${esc(d.p || d.g || "gene")}</h3>
    <div class="kv">
      ${d.lt ? `<div><span>locus tag</span><b>${esc(d.lt)}</b></div>` : ""}
      ${d.pid ? `<div><span>protein</span><b>${esc(d.pid)}</b></div>` : ""}
      <div><span>position</span><b>${fmt(d.s)}–${fmt(d.e)} (${d.st >= 0 ? "+" : "−"})</b></div>
      ${d.tf ? `<div><span>TF family</span><b>${esc(d.tf)}
        <span class="muted">(E=${esc(d.te)})</span></b></div>` : ""}
      ${d.cog != null ? `<div><span>COG assignment</span><b>${
        d.prop ? "by sequence similarity" : "by orthology"}</b></div>` : ""}
    </div>
    <div id="cogbox" class="spin">${d.cog != null ? "Loading motifs…" : ""}</div>`;
  p.classList.add("open");
  if (d.cog == null) {
    $("#cogbox").innerHTML = `<p class="muted">This gene is in no COG (cluster of
      orthologous genes), so it is drawn grey. 11.7M of the 28.9M genes in the
      collection are, and a cluster whose genes all fall outside the family's COGs
      is grey end to end.</p>`;
    $("#cogbox").classList.remove("spin");
    return;
  }
  fillCogBox(d.cog);
}

async function cogPanel(cogId) {
  $("#tooltip").style.display = "none";
  const p = $("#panel");
  p.innerHTML = `<button class="close" onclick="this.parentNode.classList.remove('open')">×</button>
    <div id="cogbox" class="spin">Loading COG…</div>`;
  p.classList.add("open");
  if (!state.selected.has(cogId)) { state.selected.add(cogId); renderChips(); repaint(); }
  fillCogBox(cogId);
}

async function fillCogBox(cogId) {
  const d = { cog: cogId };
  try {
    const r = await api(`cog/${d.cog}/motifs`);
    const c = r.cog;
    let html = `<h3 style="margin-top:14px">${esc(c.cog_name)}
        <span class="dot" style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${state.colorOf[c.cog_id]}"></span></h3>
      <div class="kv">
        <div><span>genes in COG</span><b>${c.n_seqs != null ? fmt(c.n_seqs) : "not recorded"}</b></div>
        <div><span>conservation</span><b>${c.conservation_rank != null
          ? "rank " + c.conservation_rank : "not ranked"}</b></div>
        ${c.dominant_tf_family ? `<div><span>TF family</span><b>${esc(c.dominant_tf_family)} (${c.pct_tf ?? "?"}% of genes)</b></div>` : ""}
      </div>`;
    /* n_mibig_proteins counts proteins; mibig_bgc_names is the comma-joined
       list of clusters they came from, and the two differ. */
    if (r.mibig.length) {
      const x = r.mibig[0];
      const accs = [...new Set((x.mibig_bgc_names || "").split(",")
        .filter(Boolean).map(n => n.split(".")[0]))];
      html += `<div class="kv" style="margin-top:10px"><div><span>MIBiG</span><b>${
        x.n_mibig_proteins} characterised protein${x.n_mibig_proteins === 1 ? "" : "s"}
        from ${accs.length} cluster${accs.length === 1 ? "" : "s"}</b></div></div>
        <div style="margin-top:4px">${accs.map(a =>
          `<a class="badge mibig" href="${MIBIG_URL}${esc(a)}" target="_blank"
             rel="noopener" title="open ${esc(a)} in MIBiG">${esc(a)}</a>`).join("")}</div>`;
    }
    if (!r.motifs.length) {
      html += '<p class="muted">No zoops/maxw30 motifs for this COG.</p>';
    }
    for (const m of r.motifs.slice(0, 5)) {
      html += `<div class="motifcard">
        <b>motif ${m.motif_number}</b> ${m.is_showcase ? '<span class="badge">best</span>' : ""}
        <span class="muted">E = ${esc(m.evalue?.toExponential ? m.evalue.toExponential(1) : m.evalue)}</span>
        ${m.pwm_parsed ? logoSVG(m.pwm_parsed.matrix) : ""}
        <div class="mono">${esc(m.consensus || "")}</div>
        <div class="kv">
          <div><span>coverage</span><b>${m.n_seqs_with_motif ?? "?"} / ${m.total_seqs_in_cog ?? "?"} seqs</b></div>
        </div></div>`;
    }
    $("#cogbox").innerHTML = html;
    $("#cogbox").classList.remove("spin");
  } catch (err) {
    $("#cogbox").innerHTML = '<p class="muted">Could not load motifs.</p>';
  }
}

/* ------------------------------------------------ motif cluster side panel */
async function mcPanel(mcId) {
  const p = $("#panel");
  p.innerHTML = `<button class="close" onclick="this.parentNode.classList.remove('open')">×</button>
    <h3>Motif cluster ${mcId}</h3><div id="mcbox" class="spin">Loading…</div>`;
  p.classList.add("open");
  let d;
  try { d = await api("motif-cluster/" + mcId); }
  catch { $("#mcbox").innerHTML = '<p class="muted">Could not load cluster.</p>'; return; }
  const m = d.motif_cluster;
  $("#mcbox").outerHTML = `<div id="mcbox">
    <div class="muted" style="font-size:13.5px">
      <a style="cursor:pointer;color:var(--accent)"
         onclick="go('${ssnHref(m.tf_family, m.ssn_mcl_cluster)}')"
        >${esc(ssnName(m.tf_family || "TF", m.ssn_mcl_cluster))}</a>
      ${m.family_coverage >= 0.5 ? '· <span class="badge" style="background:#ecfdf5;color:#047857">conserved</span>' : ""}
      ${m.is_best_for_ssn ? '· <span class="badge">best in cluster</span>' : ""}</div>
    ${m.pwm_parsed ? logoSVG(m.pwm_parsed.matrix) : ""}
    <div class="kv">
      <div><span>motifs</span><b>${fmt(m.n_motifs)}</b></div>
      <div><span>COGs</span><b>${fmt(m.n_cogs)}</b></div>
      <div><span>families</span><b>${m.n_families_motif} of ${m.n_families_ssn} in the
        cluster (${pct(m.family_coverage)})</b></div>
      ${m.pwm_parsed ? `<div><span>width</span><b>${m.pwm_parsed.width} bp</b></div>` : ""}
    </div>
    <div class="sec" style="margin:16px 0 6px">Member motifs</div>
    <table class="grid">
      <tr><th>family</th><th>COG</th><th class="n">E</th></tr>
      ${d.members.map(x => `
        <tr class="clk" onclick="go('family/${esc(x.family_id)}')">
          <td>${x.is_best ? "★ " : ""}<b>${esc(x.family_id || "?")}</b></td>
          <td>${esc(x.cog_name || "?")} <span class="muted">#${x.motif_number}</span></td>
          <td class="n">${x.evalue != null ? (+x.evalue).toExponential(0) : "–"}</td>
        </tr>`).join("")}
    </table></div>`;
}
