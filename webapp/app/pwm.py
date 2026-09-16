"""MEME minimal-format PWM text -> a matrix the browser can draw."""
from __future__ import annotations

import re

def parse_pwm(text: str | None):
    """MEME minimal-format .pwm text -> {width, nsites, evalue, matrix[[A,C,G,T]..]}."""
    if not text:
        return None
    matrix, meta = [], {}
    in_matrix = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("letter-probability matrix"):
            in_matrix = True
            for k, v in re.findall(r"(\w+)= *(\S+)", line):
                meta[k] = v
            continue
        if in_matrix:
            parts = line.split()
            if len(parts) == 4:
                try:
                    matrix.append([float(x) for x in parts])
                except ValueError:
                    pass
    if not matrix:
        return None
    return {
        "width": int(meta.get("w", len(matrix))),
        "nsites": int(float(meta.get("nsites", 0) or 0)),
        "evalue": meta.get("E"),
        "matrix": matrix,
    }
