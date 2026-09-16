"use strict";
/* ------------------------------------------------ routing */
function go(hash) { location.hash = hash; }
window.addEventListener("hashchange", route);

/* "#tf/9?sort=nodes" -> {path:"tf/9", seg:["tf","9"], params} */
function parseHash() {
  const raw = location.hash.replace(/^#/, "");
  const [path, qs] = raw.split("?");
  return { path, seg: path.split("/"), params: new URLSearchParams(qs || "") };
}

/* Which nav tab owns a path. Matched on whole segments, so #families and
   #family/FAM1 cannot collide. */
const NAV = {
  "nav-home":      p => p === "",
  "nav-families":  p => p === "families" || p.startsWith("family/"),
  "nav-tf":        p => p === "tf" || p.startsWith("tf/") || p.startsWith("ssn/"),
  "nav-downloads": p => p === "downloads",
};

/* Every page function takes the route generation `my` and re-checks stale()
   after every await before touching the DOM. */
let routeId = 0;
const stale = my => my !== routeId;

function route() {
  const { path, seg, params } = parseHash();
  const my = ++routeId;
  $("#panel").classList.remove("open");
  for (const id in NAV) $("#" + id)?.classList.toggle("on", NAV[id](path));
  switch (seg[0]) {
    case "":          return home(my);
    case "families":  return familiesPage(params, my);
    case "family":    return familyPage(seg[1], my);  // ids are all FAM\d+, no decode
    case "ssn":       return seg[2] !== undefined
                        ? ssnPage(decodeURIComponent(seg[1]), +seg[2], my)
                        : ssnRedirect(+seg[1], my);  // bare #ssn/{ssn_id}: resolve the surrogate
    case "tf":        return seg[1] !== undefined ? ssnListPage(+seg[1], my) : tfHome(my);
    case "downloads": return downloadsPage(my);
    default:          return notFound(path);
  }
}

function notFound(path) {
  $("#main").innerHTML = `<h2>Page not found</h2>
    <p class="muted">There is nothing at <span class="seq">#${esc(path)}</span>.</p>
    <p><span class="navlink" style="padding-left:0" onclick="go('')">← Home</span></p>`;
}
