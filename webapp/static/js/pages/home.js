"use strict";
/* ------------------------------------------------ home / about
   Deliberately short. Methods and validation detail live in the paper. */
async function home(my) {
  $("#main").innerHTML = '<div class="spin">Loading…</div>';
  let m;
  try { m = await api("meta"); }
  catch { if (!stale(my)) $("#main").innerHTML = '<p class="muted">Could not load site statistics.</p>'; return; }
  if (stale(my)) return;
  const c = m.counts;
  const stat = (v, l) => `<div class="stat"><b>${fmt(v)}</b><span>${l}</span></div>`;

  $("#main").innerHTML = `
    <div class="eyebrow">King's College London · Qsys Lab</div>
    <h2>Conserved regulatory motifs in biosynthetic gene clusters</h2>
    <p class="lede prose">A computational resource for exploring pathway-specific
      transcription factors and upstream regulatory motifs across
      ${fmt(c.families_with_motifs)} BGC families derived from the BiG-FAM database.</p>

    <div class="stats">
      ${stat(c.families, "gene cluster families")}
      ${stat(c.bgcs, "BGCs")}
      ${stat(c.species, "species")}
      ${stat(c.families_with_motifs, "families with motifs")}
    </div>

    <div class="cards" style="grid-template-columns:repeat(auto-fill,minmax(280px,1fr))">
      <div class="card" onclick="go('families')">
        <h3>Families →</h3>
        <div class="muted" style="font-size:14px">Search and filter gene cluster
          families by product class, size and taxonomy. Each family page draws its
          BGCs as gene tracks coloured by cluster of orthologous genes (COG), with
          the motif predicted upstream of each COG.</div>
      </div>
      <div class="card" onclick="go('tf')">
        <h3>Regulators →</h3>
        <div class="muted" style="font-size:14px">Transcription-factor regulators
          clustered by sequence similarity, the motifs recovered within those
          clusters, and how they compare to experimentally known binding sites in
          PRODORIC.</div>
      </div>
      <div class="card" onclick="go('downloads')">
        <h3>Downloads →</h3>
        <div class="muted" style="font-size:14px">The motif tables, family
          assignments and regulator clusters behind the site, packaged as a single
          archive.</div>
      </div>
    </div>

    <div class="sec">How it was built</div>
    <figure class="mfig">
      <img src="/static/method-overview.svg"
           alt="Method overview: genes in BGC families from BiG-FAM are grouped into
                clusters of orthologous genes (COGs), upstream regions are searched for
                motifs with MEME, regulators are clustered by sequence similarity, and
                motifs are compared to PRODORIC.">
    </figure>
    <div class="prose note">
      <p>BGC families come from BiG-FAM. Within each family the genes are grouped into
        clusters of orthologous genes (COGs), the region upstream of each COG is
        extracted, and MEME searches it for a shared motif; TF annotation against the
        ENTRAF database across the whole BiG-FAM dataset gives each family its
        pathway-specific TFs (<b>A</b>). Those TFs are clustered by sequence
        similarity, motifs recurring across different BGC families are grouped into
        motif clusters, and each motif cluster is compared against PRODORIC with
        Tomtom to see whether a known binding site is recovered (<b>B</b>).</p>
      <p>Every motif here is a computational prediction; only the PRODORIC matches
        carry experimental support. ${SITE.paper
          ? `Full methods, parameters and validation are in the paper:
             <a href="${SITE.paper}" target="_blank" rel="noopener">read it here</a>.`
          : `Full methods, parameters and validation will be in the paper, which is
             in preparation.`}</p>
    </div>

    <p class="note" style="margin-top:24px">Data build ${esc(m.build.built_at || "")} ·
      motif setting <span class="seq">${esc(m.build.showcase_param || "")}</span></p>`;
}
