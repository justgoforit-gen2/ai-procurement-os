"""Spend analysis module."""
from __future__ import annotations

from proc_core.spend.loader import load_all
from proc_core.spend.quality import check as quality_check
from proc_core.spend.spend_overview import build_cube, period_over_period
from proc_core.spend.concentration import category_concentration, supplier_concentration
from proc_core.spend.price_variance import by_category as price_by_category, by_dimension as price_by_dimension
from proc_core.spend.compliance import maverick_summary, channel_compliance, split_order_detection, all_findings
from proc_core.spend.improvement_mining import mine as improvement_mine
from proc_core.spend.kpi import load_kpi_config, compute_kpi, compute_milestones

__all__ = [
    "load_all",
    "quality_check",
    "build_cube",
    "period_over_period",
    "category_concentration",
    "supplier_concentration",
    "price_by_category",
    "price_by_dimension",
    "maverick_summary",
    "channel_compliance",
    "split_order_detection",
    "all_findings",
    "improvement_mine",
    "load_kpi_config",
    "compute_kpi",
    "compute_milestones",
]
