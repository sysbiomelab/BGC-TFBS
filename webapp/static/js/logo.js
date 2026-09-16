"use strict";
/* ------------------------------------------------ sequence logo from PWM */
function logoSVG(matrix) {
  const COL = { A: "#22c55e", C: "#3b82f6", G: "#f59e0b", T: "#ef4444" };
  const LETTERS = ["A", "C", "G", "T"];
  const W = 16, H = 64, ASC = 0.72;          // glyph ascent fraction of font-size
  const w = matrix.length * W;
  let cols = "";
  matrix.forEach((probs, i) => {
    const ic = 2 + probs.reduce((s, p) => p > 0 ? s + p * Math.log2(p) : s, 0); // 0..2 bits
    let y = H;                                 // stack letters from the bottom up
    probs.map((p, j) => [p, LETTERS[j]])
      .sort((a, b) => a[0] - b[0])
      .forEach(([p, L]) => {
        const hh = (p * ic / 2) * H;
        if (hh < 0.8) return;
        y -= hh;
        cols += `<g transform="translate(${i * W},${y + hh}) scale(1,${(hh / (H * ASC)).toFixed(4)})">
          <text x="${W / 2}" y="0" font-size="${H}" text-anchor="middle"
            textLength="${W - 2}" lengthAdjust="spacingAndGlyphs"
            font-family="Arial, Helvetica, sans-serif" font-weight="bold"
            fill="${COL[L]}">${L}</text></g>`;
      });
  });
  return `<svg viewBox="0 0 ${w} ${H}" width="100%" preserveAspectRatio="xMinYMid meet"
      style="max-width:${w * 1.4}px;display:block;margin:6px 0;background:#fafaf8;border-radius:4px">
    ${cols}</svg>`;
}
