"""
Wagestop — National Insurance Calculation Engine
Layer 1: Monthly and weekly, all NI categories, 2024/25 and 2025/26.
"""

from typing import Tuple, List
from .models import NIBreakdown, TaxYear


# ---------------------------------------------------------------------------
# NI THRESHOLDS
# ---------------------------------------------------------------------------

NI_THRESHOLDS = {
    TaxYear.Y2024_25: {
        "monthly": {
            "LEL": 542.00,
            "ST":  758.00,
            "PT":  1048.00,
            "UEL": 4189.00,
        },
        "weekly": {
            "LEL": 125.00,
            "ST":  175.00,
            "PT":  242.00,
            "UEL": 967.00,
        },
        "er_rate": 0.138,       # 13.8% in 2024/25
        "er_threshold": "ST",
    },
    TaxYear.Y2025_26: {
        "monthly": {
            "LEL": 542.00,
            "ST":  417.00,
            "PT":  1048.00,
            "UEL": 4189.00,
        },
        "weekly": {
            "LEL": 125.00,
            "ST":  96.00,
            "PT":  242.00,
            "UEL": 967.00,
        },
        "er_rate": 0.15,        # 15% from April 2025
        "er_threshold": "ST",
    },
    TaxYear.Y2026_27: {
        "monthly": {
            "LEL": 542.00,
            "ST":  417.00,
            "PT":  1048.00,
            "UEL": 4189.00,
        },
        "weekly": {
            "LEL": 125.00,
            "ST":  96.00,
            "PT":  242.00,
            "UEL": 967.00,
        },
        "er_rate": 0.15,
        "er_threshold": "ST",
    },
}

# ---------------------------------------------------------------------------
# NI CATEGORY RATES
# Employee rates: (PT_to_UEL_rate, above_UEL_rate)
# ---------------------------------------------------------------------------

NI_CATEGORY_EE_RATES = {
    "A": (0.08,  0.02),
    "B": (0.0185, 0.02),
    "C": (0.00,  0.00),     # Over state pension age — no Ee NI
    "D": (0.08,  0.02),
    "E": (0.08,  0.02),
    "F": (0.08,  0.02),
    "H": (0.08,  0.02),
    "I": (0.0185, 0.02),
    "J": (0.02,  0.02),     # Deferment
    "K": (0.02,  0.02),
    "L": (0.02,  0.02),
    "M": (0.00,  0.00),     # Under 21 — no Ee NI below UEL
    "N": (0.0185, 0.02),
    "S": (0.00,  0.00),     # Freeport — no Ee NI below UST
    "V": (0.00,  0.00),
    "Z": (0.00,  0.02),     # Under 21 apprentice
}


# ---------------------------------------------------------------------------
# MAIN NI CALCULATION
# ---------------------------------------------------------------------------

def calculate_ni(gross_for_ni: float,
                 ni_category: str,
                 tax_year: TaxYear,
                 frequency: str = "monthly") -> NIBreakdown:
    """
    Calculate employee and employer NI for a pay period.
    Returns full NIBreakdown including drill-down workings.

    gross_for_ni: NI-able earnings for this period
                  (built from pay lines — Tronc/expenses excluded,
                   salary sacrifice already deducted)
    """
    config = NI_THRESHOLDS[tax_year]
    thresholds = config[frequency]
    er_rate = config["er_rate"]
    category = ni_category.upper()

    lel = thresholds["LEL"]
    st  = thresholds["ST"]
    pt  = thresholds["PT"]
    uel = thresholds["UEL"]

    ee_pt_rate, ee_above_uel_rate = NI_CATEGORY_EE_RATES.get(
        category, (0.08, 0.02)
    )

    bands = []
    ee_ni = 0.0
    er_ni = 0.0

    # Sage displays UEL when earnings exceed it — flag for UI
    sage_uel_display = gross_for_ni > uel

    # --- Employee NI ---
    if gross_for_ni > pt:
        # PT to UEL band
        pt_to_uel = min(gross_for_ni, uel) - pt
        ee_pt_band = round(pt_to_uel * ee_pt_rate, 2)
        bands.append({
            "band": "PT to UEL",
            "from": pt,
            "to": min(gross_for_ni, uel),
            "rate": ee_pt_rate,
            "ni": ee_pt_band,
            "type": "employee",
        })
        ee_ni += ee_pt_band

    if gross_for_ni > uel:
        # Above UEL band — NI continues at 2%, does NOT stop
        above_uel = gross_for_ni - uel
        ee_above_band = round(above_uel * ee_above_uel_rate, 2)
        bands.append({
            "band": "Above UEL",
            "from": uel,
            "to": gross_for_ni,
            "rate": ee_above_uel_rate,
            "ni": ee_above_band,
            "type": "employee",
        })
        ee_ni += ee_above_band

    # --- Employer NI ---
    # Cat C: no Ee NI but Er NI still applies
    if gross_for_ni > st:
        er_band = round((gross_for_ni - st) * er_rate, 2)
        bands.append({
            "band": "Er: above ST",
            "from": st,
            "to": gross_for_ni,
            "rate": er_rate,
            "ni": er_band,
            "type": "employer",
        })
        er_ni = er_band

    return NIBreakdown(
        ni_category=category,
        gross_for_ni=gross_for_ni,
        bands_applied=bands,
        ee_ni_calculated=round(ee_ni, 2),
        er_ni_calculated=round(er_ni, 2),
        sage_uel_display=sage_uel_display,
    )
