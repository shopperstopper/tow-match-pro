"""Tow Match Pro inventory completeness report.

Run after any dealer adapter produces a normalized CSV. This does not decide
compatibility; it reports whether the feed contains the source facts needed by
our three matching engines and highlights parsing/data-quality issues.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd

COMMON = ["stock_number", "rv_category", "condition", "location", "inventory_status", "sellable", "overall_length_ft"]
CATEGORY_FIELDS = {
    "Travel Trailer": ["uvw_lb", "gvwr_lb", "published_hitch_pin_lb"],
    "Fifth Wheel": ["uvw_lb", "gvwr_lb", "published_hitch_pin_lb"],
    "Truck Camper": ["uvw_lb", "fresh_water_gal", "truck_bed_size", "body_style", "cg_front_in"],
}

def pct(series: pd.Series) -> float:
    if len(series) == 0: return 0.0
    present = series.notna() & series.astype(str).str.strip().ne("")
    return round(100 * present.mean(), 1)

def report(df: pd.DataFrame) -> str:
    lines = [f"# Inventory Data Quality Report", "", f"Records: **{len(df):,}**", ""]
    lines += ["## Common fields", "", "| Field | Present |", "|---|---:|"]
    for f in COMMON:
        lines.append(f"| {f} | {pct(df[f]) if f in df else 0:.1f}% |")
    if "rv_category" in df:
        lines += ["", "## Category-specific matching inputs", ""]
        for cat, fields in CATEGORY_FIELDS.items():
            sub = df[df["rv_category"].eq(cat)]
            lines += [f"### {cat} ({len(sub):,})", "", "| Field | Present |", "|---|---:|"]
            for f in fields:
                lines.append(f"| {f} | {pct(sub[f]) if f in sub else 0:.1f}% |")
            lines.append("")
    if "parse_warnings" in df:
        warnings = df["parse_warnings"].fillna("").astype(str).str.strip()
        n = warnings.ne("").sum()
        lines += ["## Parser warnings", "", f"Records with warnings: **{n:,}** ({(100*n/len(df) if len(df) else 0):.1f}%)", ""]
        if n:
            for msg, count in warnings[warnings.ne("")].value_counts().head(10).items():
                lines.append(f"- {count} × {msg}")
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser(); p.add_argument("csv"); p.add_argument("--output", default="inventory_data_quality.md")
    a=p.parse_args(); df=pd.read_csv(a.csv); text=report(df); Path(a.output).write_text(text); print(text)
if __name__ == "__main__": main()
