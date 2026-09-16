"use strict";
/* One table per manifest folder. Without BGC_TFBS_DOWNLOADS_LIVE on the
   server there are no file URLs: names render as plain text and the page says so. */
async function downloadsPage(my) {
  $("#main").innerHTML = '<div class="spin">Loading…</div>';
  let a;
  try { a = await api("downloads"); }
  catch { if (!stale(my)) $("#main").innerHTML = '<p class="muted">Could not load downloads.</p>'; return; }
  if (stale(my)) return;
  const contact = a.contact
    ? ` Contact <a class="ext" href="mailto:${esc(a.contact)}">${esc(a.contact)}</a> if you
       need any of it before then.` : "";
  const fileCell = f => f.url
    ? `<a class="ext" href="${esc(f.url)}" title="download ${esc(f.name)}">${esc(f.name)}</a>`
    : `<span class="seq">${esc(f.name)}</span>`;

  $("#main").innerHTML = `
    <h2>Downloads</h2>
    <p class="muted" style="max-width:76ch">The full dataset is one Zenodo record:
      <a class="ext" href="${esc(a.doi_url)}" target="_blank" rel="noopener">doi:${esc(a.doi)}</a>
      · ${esc(a.total_size)}.${
      a.readme ? ` The record's ${a.readme.url
        ? `<a class="ext" href="${esc(a.readme.url)}" target="_blank" rel="noopener">README</a>`
        : "README"} describes every file.` : ""}</p>
    ${a.live ? "" : `<p class="widen"><b>Available on publication.</b> The record is
      private until the paper is submitted, so the files below are listed but not
      yet downloadable.${contact}</p>`}
    ${!a.groups.length ? '<p class="muted">No file list is available on this server.</p>' : ""}
    ${a.groups.map(g => `
      <div class="sec">${esc(g.title)}</div>
      <p class="note" style="max-width:76ch;margin:0 0 8px">${esc(g.blurb)}</p>
      <div style="overflow-x:auto"><table class="grid dl">
        <tr><th>file</th><th class="n">size</th></tr>
        ${g.files.map(f => `<tr>
          <td>${fileCell(f)}</td>
          <td class="n" style="white-space:nowrap">${esc(f.size)}</td></tr>`).join("")}
      </table></div>`).join("")}`;
}
