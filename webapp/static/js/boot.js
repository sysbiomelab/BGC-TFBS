"use strict";
/* Every load-time side effect lives here, so this file must load last. The
   other scripts only declare, so their order is free. */

function renderFooter() {
  const L = SITE.licence, O = SITE.org;
  $("#foot").innerHTML = `
    <div class="in">
      <div class="org">
        ${O.logo ? `<img class="logo" src="${O.logo}" alt="${esc(O.inst)}">` : ""}
        <b>${esc(O.lab)}</b><br>
        ${esc(O.centre)}<br>
        ${esc(O.inst)}<br>
        ${esc(O.address)}
      </div>
      <div class="mid">
        <div class="links">
          <a href="mailto:${SITE.contact}">Contact</a>
          <a href="${SITE.repo}" target="_blank" rel="noopener">GitHub</a>
          ${SITE.paper ? `<a href="${SITE.paper}" target="_blank" rel="noopener">Paper</a>` : ""}
          <a href="${SITE.data.url}" target="_blank" rel="noopener"
             title="the full dataset on Zenodo, doi:${SITE.data.doi}">Data</a>
        </div>
        <div class="cite">${esc(SITE.cite)}</div>
      </div>
      <div class="lic">
        <a class="ccbadge" href="${L.url}" target="_blank" rel="noopener license"
          title="${esc(L.name)}"><img src="${L.badge}" alt="${esc(L.short)}"
          ><span class="ccalt" hidden>${esc(L.short)}</span></a>
        BGC-TFBS is licensed under a
        <a href="${L.url}" target="_blank" rel="noopener license">${esc(L.name)}</a>.
        Source annotations carry their own terms; the site code is MIT.
      </div>
    </div>`;
  /* both images are optional: a failed CC button falls back to the text badge,
     a failed logo is dropped */
  for (const img of $("#foot").querySelectorAll("img"))
    img.addEventListener("error", () => {
      const alt = img.parentElement.querySelector(".ccalt");
      if (alt) alt.hidden = false;
      img.remove();
    });
}

/* ------------------------------------------------ header height
   #chiprow and #panel stick under the header, which wraps on narrow screens.
   offsetHeight, not contentRect.height: padding and border are part of it. */
const hdrEl = document.querySelector("header");
const syncHdr = () =>
  document.documentElement.style.setProperty("--hdr", hdrEl.offsetHeight + "px");
new ResizeObserver(syncHdr).observe(hdrEl);

renderFooter();
syncHdr();
route();
