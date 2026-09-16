"use strict";
/* ------------------------------------------------ family page */
const state = { fam: null, cogs: [], colorOf: {}, selected: new Set(),
                offset: 0, total: 0, bgcs: [], allChips: false,
                mibig: null, allMibig: false };

async function familyPage(famId, my) {
  $("#main").innerHTML = '<div class="spin">Loading ' + esc(famId) + "…</div>";
  let d;
  try { d = await api("family/" + encodeURIComponent(famId)); }
  catch { if (!stale(my)) $("#main").innerHTML = "<p>Family not found.</p>"; return; }
  if (stale(my)) return;

  state.fam = d.family; state.cogs = d.cogs; state.selected = new Set();
  state.offset = 0; state.bgcs = []; state.colorOf = {}; state.allChips = false;
  state.mibig = null; state.allMibig = false;
  /* colour from color_rank, never conservation_rank: the API fills color_rank
     even for a COG that has no rank */
  for (const c of d.cogs) state.colorOf[c.cog_id] = cogColor(c.color_rank);

  const f = d.family;
  const tfCogs = d.cogs.filter(c => c.dominant_tf_family);
  state.mibig = d.mibig || { bgcs: [] };
  const kv = (k, v) => `<div><span>${k}</span><b>${v}</b></div>`;

  $("#main").innerHTML = `
    <h2 class="famhead">${esc(f.family_id)}</h2>

    <div class="fgrid">
      <section class="box">
        <h3>Family overview</h3>
        <div class="kv">
          ${kv("BGC class", esc(f.dominant_class || "unknown"))}
          ${kv("Total BGCs", fmt(f.n_bgcs))}
          ${kv("Genes", fmt(f.total_cds))}
          ${kv("COGs", fmt(d.cogs.length))}
          ${kv("Phyla", fmt(f.n_phyla))}
          ${kv("Genera", fmt(f.n_genera))}
          ${kv("Species", fmt(f.n_species))}
          ${kv("COGs with a motif", fmt(f.n_cogs_meme ?? 0))}
        </div>
        <div style="margin-top:10px">${[[f.has_motif_data, "motif data"],
            [f.has_cog_data, "COG data"], [f.has_tf_data, "TF annotation"]]
          .map(([on, t]) => `<span class="badge${on ? "" : " off"}">${t}</span>`).join("")}</div>
        <p class="note" style="margin:8px 0 0">${d.class_breakdown.map(x =>
            esc(x.class) + " (" + fmt(x.n) + ")").join(" · ")}</p>
      </section>

      <section class="box">
        <h3>Pathway-specific TFs</h3>
        ${tfCogs.length ? `<table class="mini">
          <tr><th>COG</th><th>TF family</th><th class="n">genes</th></tr>
          ${tfCogs.slice(0, 8).map(c => `<tr class="clk" onclick="cogShow(${c.cog_id})">
            <td><span class="dot" style="background:${state.colorOf[c.cog_id]}"></span>
              ${esc(c.cog_name)}</td>
            <td><b>${esc(c.dominant_tf_family)}</b></td>
            <td class="n">${fmt(c.n_seqs)}</td></tr>`).join("")}
        </table>${tfCogs.length > 8
          ? `<p class="note">and ${tfCogs.length - 8} more</p>` : ""}`
        : `<p class="muted" style="font-size:14px">No COG in this family
            carries a dominant TF family. Only 5,940 of the ${fmt(126790)} COGs in the
            collection do, so this is the common case rather than a gap in the page.</p>`}
      </section>

      <section class="box" id="mibigbox" hidden></section>
    </div>

    <section class="box">
      <h3>Gene cluster viewer <span class="muted" style="font-weight:400;text-transform:none">
        click a COG (cluster of orthologous genes) to highlight it and see its
        predicted motifs; <b>●</b> marks a COG that has one</span></h3>
      <div id="chiprow"></div>
      <p id="covnote" class="note"></p>
      <div id="tracks"></div>
      <button id="bgc-more" class="loadmore" hidden onclick="loadBGCs()">Load more BGCs</button>
    </section>`;
  renderChips();
  renderMibig();
  loadBGCs();
}

/* ------------------------------------------------ MIBiG
   Which COG each characterised protein landed in is shown in the COG side
   panel, not here. */
function renderMibig() {
  const box = $("#mibigbox");
  if (!box) return;
  const mib = state.mibig || { bgcs: [] };
  if (!mib.bgcs.length) { box.hidden = true; return; }
  const shown = state.allMibig ? mib.bgcs : mib.bgcs.slice(0, 6);
  box.hidden = false;
  box.innerHTML = `
    <h3>MIBiG reference clusters</h3>
    <table class="mini">
      <tr><th>accession</th><th>organism</th><th>class</th><th class="n">genes</th></tr>
      ${shown.map(b => `<tr>
        <td><a class="badge mibig" href="${MIBIG_URL}${esc(b.accession)}" target="_blank"
          rel="noopener" title="open ${esc(b.accession)} in MIBiG">${esc(b.accession)}</a></td>
        <td class="muted"><i>${esc(b.species || "–")}</i></td>
        <td class="muted">${esc(b.class || "–")}</td>
        <td class="n">${fmt(b.n_cds)}</td></tr>`).join("")}
    </table>
    ${mib.bgcs.length > 6 ? `<p class="note" style="margin:8px 0 0"><span class="navlink"
      style="padding:0" onclick="state.allMibig=!state.allMibig;renderMibig()">${
      state.allMibig ? "show fewer" : `show all ${mib.bgcs.length}`}</span></p>` : ""}
`;
}

/* ------------------------------------------------ COG chips */
function renderChips() {
  const N = 14;
  /* Ordered for clicking, not by conservation: COGs with a motif first, then
     those with a TF, then by rank. Otherwise the default N chips can hold no
     COG with a motif. */
  const cogs = state.cogs.slice().sort((a, b) =>
       (b.has_showcase ? 1 : 0) - (a.has_showcase ? 1 : 0)
    || (b.dominant_tf_family ? 1 : 0) - (a.dominant_tf_family ? 1 : 0)
    || (a.color_rank ?? 1e9) - (b.color_rank ?? 1e9));
  const shown = state.allChips ? cogs : cogs.slice(0, N);
  const chip = c => `
    <span class="chip ${state.selected.has(c.cog_id) ? "sel" : ""}"
          onclick="cogShow(${c.cog_id})"
          title="${c.n_seqs != null ? fmt(c.n_seqs) + " genes" : "gene count not recorded"}${
            c.conservation_rank != null ? " · conservation rank " + c.conservation_rank : ""}${
            c.dominant_tf_family ? " · TF: " + esc(c.dominant_tf_family) : ""}">
      <span class="dot" style="background:${state.colorOf[c.cog_id]}"></span>
      ${esc(c.cog_name)}${c.dominant_tf_family ? " ⚑" : ""}${c.has_showcase ? " ●" : ""}
    </span>`;
  const more = cogs.length > N
    ? `<span class="chip clear" onclick="state.allChips=!state.allChips;renderChips()">${
        state.allChips ? "show fewer" : `show all ${cogs.length} COGs`}</span>` : "";
  $("#chiprow").innerHTML = shown.map(chip).join("") + more +
    (state.selected.size ? `<span class="chip clear" onclick="clearSel()">clear</span>` : "") +
    `<span class="chip legend" title="a gene in no COG -- 11.7M of the
      28.9M genes in the collection, so a cluster can be entirely grey">
      <span class="dot" style="background:var(--grey-gene)"></span>no COG</span>
     <span class="chip legend" title="this COG has a predicted motif; click it to
       see the motif and its logo">● has a motif</span>`;
}

function cogShow(id) {
  if (state.selected.has(id)) {
    state.selected.delete(id);
    renderChips(); repaint();
    $("#panel").classList.remove("open");
    return;
  }
  cogPanel(id);                      // selects, repaints, then loads the motifs
}

function clearSel() { state.selected.clear(); renderChips(); repaint(); }

async function loadBGCs() {
  const fam = state.fam.family_id;
  $("#bgc-more").hidden = true;
  const d = await api(`family/${encodeURIComponent(fam)}/bgcs?offset=${state.offset}&limit=20`);
  // the page may have been replaced while this was in flight
  if (!$("#tracks") || state.fam.family_id !== fam) return;
  state.total = d.total;
  for (const b of d.bgcs) { state.bgcs.push(b); $("#tracks").appendChild(trackEl(b)); }
  state.offset += d.bgcs.length;
  $("#bgc-more").hidden = state.offset >= state.total;
  $("#bgc-more").textContent = `Load more BGCs (${state.offset} / ${fmt(state.total)})`;
  renderCoverage();
  repaint();
}

/* An all-grey cluster is not a rendering failure; the note says which case
   this family is in. */
function renderCoverage() {
  const el = $("#covnote");
  if (!el) return;
  let tot = 0, inGroup = 0;
  for (const b of state.bgcs)
    for (const c of b.cds) { tot++; if (c.cog_id != null) inGroup++; }
  if (!tot) { el.textContent = ""; return; }
  const shown = `${fmt(state.bgcs.length)} of ${fmt(state.total)} clusters loaded`;
  el.innerHTML = inGroup === 0
    ? `${shown}. <b>None</b> of these ${fmt(tot)} genes is assigned to a COG,
       so every cluster is drawn grey. This family's ${fmt(state.cogs.length)}
       COGs exist and carry motifs, but the gene-to-COG assignment has not been
       propagated for it yet. The motifs above are unaffected.`
    : `${shown}. ${fmt(inGroup)} of ${fmt(tot)} genes (${Math.round(100 * inGroup / tot)}%)
       are in one of this family's ${fmt(state.cogs.length)} COGs; the rest are in no
       COG and stay grey.`;
}
