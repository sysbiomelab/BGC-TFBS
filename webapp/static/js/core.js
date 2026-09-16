"use strict";
/* Loaded as a classic script, never type="module": every handler in the
   markup is an inline onclick=, which resolves against the global scope. */

const $ = s => document.querySelector(s);
const api = p => fetch("/api/" + p).then(r => { if (!r.ok) throw r; return r.json(); });
/* ' must be escaped: trackEl() interpolates esc() into a single-quoted
   data-cds attribute, and an early quote breaks JSON.parse in the handlers. */
const esc = s => (s ?? "").toString().replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = n => n == null ? "–" : Number(n).toLocaleString();

/* Site identity. The footer and the Home page both read from this. */
const SITE = {
  contact: "idris.matine@kcl.ac.uk",
  repo:    "https://github.com/sysbiomelab/BGC-TFBS",
  /* empty hides the footer Paper link and Home's "read it here" call */
  paper:   "",
  cite:    "Paper in preparation.",
  data: { doi: "10.5281/zenodo.22766286", url: "https://doi.org/10.5281/zenodo.22766286" },
  licence: {
    short: "CC BY 4.0",
    name:  "Creative Commons Attribution 4.0 International License",
    url:   "https://creativecommons.org/licenses/by/4.0/",
    /* served locally: no page view calls out to creativecommons.org */
    badge: "/static/cc-by.svg",
  },
  org: {
    lab:     "Qsys Lab",
    centre:  "Centre for Host-Microbiome Interactions (CHMI)",
    inst:    "King's College London",
    address: "Guy's Campus, London SE1 1UL, United Kingdom",
    /* empty means no <img> is rendered; the text lockup names the institution */
    logo:    "",
  },
};

/* /go/{accession} redirects to the current MIBiG version: link the bare
   accession, without the stored version suffix. */
const MIBIG_URL = "https://mibig.secondarymetabolites.org/go/";

/* golden-angle colour per conservation_rank — stable, spreads consecutive ranks */
const cogColor = rank => rank == null ? "var(--grey-gene)"
  : `hsl(${(rank * 137.508) % 360} 62% 52%)`;
