"use strict";
/* One SVG per BGC. Reads `state`, which pages/family.js owns. */

function trackEl(b) {
  const W = 1120, H = 34, mid = 17, h = 14;
  const div = document.createElement("div");
  div.className = "track";
  const span = Math.max(b.length_nt || 1,
    ...b.cds.map(c => c.nt_end || 0));
  const x = nt => (nt / span) * W;
  let genes = "";
  for (const c of b.cds) {
    const x1 = x(c.nt_start), x2 = x(c.nt_end);
    const w = Math.max(x2 - x1, 2), head = Math.min(7, w);
    const fwd = (c.strand ?? 1) >= 0;
    const pts = fwd
      ? `${x1},${mid - h/2} ${x1 + w - head},${mid - h/2} ${x1 + w},${mid} ${x1 + w - head},${mid + h/2} ${x1},${mid + h/2}`
      : `${x1 + head},${mid - h/2} ${x1 + w},${mid - h/2} ${x1 + w},${mid + h/2} ${x1 + head},${mid + h/2} ${x1},${mid}`;
    genes += `<polygon class="gene" points="${pts}" data-cog="${c.cog_id ?? ""}"
      data-cds='${esc(JSON.stringify({g:c.gene_key,p:c.product,s:c.nt_start,e:c.nt_end,
        st:c.strand,tf:c.tf_family,te:c.tf_evalue,cog:c.cog_id,
        prop:c.cog_is_propagated,lt:c.locus_tag,pid:c.protein_id}))}'></polygon>`;
  }
  div.innerHTML = `
    <div class="lbl"><b>${esc(b.bgc_name)}</b>
      <span class="muted">${esc(b.species || b.organism || "")}</span>
      <span class="muted">${fmt(b.length_nt)} nt · ${b.cds.length} genes ·
        ${esc(b.class || "")}</span>
      ${b.bgc_type === "mibig"
        ? `<a class="badge mibig" href="${MIBIG_URL}${esc(b.bgc_name.split(".")[0])}"
             target="_blank" rel="noopener"
             title="characterised cluster, open in MIBiG">MIBiG</a>` : ""}</div>
    <svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}">
      <line x1="0" y1="${mid}" x2="${W}" y2="${mid}" stroke="var(--line)"/>
      ${genes}</svg>`;
  div.querySelectorAll(".gene").forEach(g => {
    g.addEventListener("mousemove", showTip);
    g.addEventListener("mouseleave", () => $("#tooltip").style.display = "none");
    g.addEventListener("click", geneClick);
  });
  return div;
}

function repaint() {
  /* Selection keeps every COG's colour: selected genes get .sel, the rest
     .dim; no-COG genes stay grey either way. */
  const any = state.selected.size > 0;
  document.querySelectorAll(".gene").forEach(g => {
    const cog = g.dataset.cog ? Number(g.dataset.cog) : null;
    g.setAttribute("fill",
      cog == null ? "var(--grey-gene)" : (state.colorOf[cog] || "var(--grey-gene)"));
    const sel = any && cog != null && state.selected.has(cog);
    g.classList.toggle("sel", sel);
    g.classList.toggle("dim", any && !sel);
  });
}

function showTip(e) {
  const d = JSON.parse(e.target.dataset.cds);
  const cogName = d.cog != null
    ? (state.cogs.find(c => c.cog_id === d.cog)?.cog_name ?? "COG " + d.cog) : null;
  $("#tooltip").innerHTML = `
    <b>${esc(d.p || d.g || "gene")}</b><br>
    <span class="t2">${esc(d.g || "")} · ${fmt(d.s)}–${fmt(d.e)} (${d.st >= 0 ? "+" : "−"})</span><br>
    ${cogName ? `<span class="t2">${esc(cogName)}${d.prop ? " (propagated)" : ""}</span><br>` : ""}
    ${d.tf ? `<span class="t2">TF: ${esc(d.tf)} (E=${esc(d.te)})</span>` : ""}`;
  $("#tooltip").style.display = "block";
  $("#tooltip").style.left = Math.min(e.clientX + 14, innerWidth - 330) + "px";
  $("#tooltip").style.top = (e.clientY + 14) + "px";
}
