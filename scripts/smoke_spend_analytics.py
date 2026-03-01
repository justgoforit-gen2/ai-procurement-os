"""Smoke test for Spend Analytics without Playwright.

Goal:
- Catch runtime errors in the spend analytics pipeline (data load → checks → analytics)
  without relying on Playwright/browser automation.

Run:
  uv run python scripts/smoke_spend_analytics.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from proc_core.spend.loader import load_all
from proc_core.spend.quality import check as quality_check
from proc_core.spend.spend_overview import build_cube
from proc_core.spend.concentration import supplier_concentration
from proc_core.spend.price_variance import by_category as price_by_category
from proc_core.spend.compliance import maverick_summary, all_findings
from proc_core.spend.improvement_mining import mine as improvement_mine


def main() -> int:
    project_root = Path(__file__).parents[1]
    data_dir = project_root / "data" / "samples"

    df_po_raw, df_items, df_suppliers = load_all(
        data_dir,
        mapping="default",
        config_root=project_root,
    )

    report = quality_check(df_po_raw)
    df_clean: pd.DataFrame = report["df_clean"]

    # Core analytics: just ensure they run without exceptions
    _ = build_cube(df_clean)
    conc = supplier_concentration(df_clean)
    pv = price_by_category(df_clean)
    mav = maverick_summary(df_clean)
    findings = all_findings(df_clean)
    improvements = improvement_mine(df_clean)

    # Minimal sanity outputs (avoid printing sensitive contents)
    print("OK: smoke_spend_analytics")
    print(f"rows_raw={len(df_po_raw):,} rows_clean={len(df_clean):,} issues={report['summary']['issue_count']:,}")
    print(f"cube_rows={len(_):,} suppliers_ranked={len(conc['ranked_df']):,} pv_rows={len(pv):,}")
    print(f"mav_rows={len(mav):,} findings_rows={len(findings):,} improvement_rows={len(improvements):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
