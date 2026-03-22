"""
Wagestop — Tax Calculation Engine
Handles income tax calculation for all standard tax codes.
Layer 1: Monthly, England/Wales, standard L/K/BR/D0/D1/NT/0T codes.
Layer 4 (future): Scottish S prefix codes.
"""

import math
from typing import Tuple, Optional, List
from .models import TaxBreakdown, TaxYear


# ---------------------------------------------------------------------------
# TAX YEAR CONFIGURATION
# ---------------------------------------------------------------------------

TAX_CONFIG = {
    TaxYear.Y2024_25: {
        "monthly_basic_ceiling": 3141.67,       # £37,700 ÷ 12
        "monthly_higher_ceiling": 10428.33,     # £125,140 ÷ 12 (was lower)
        "basic_rate": 0.20,
        "higher_rate": 0.40,
        "additional_rate": 0.45,
        "batch_annual": 5000.04,
        "scottish_bands": [
            {"name": "Starter",      "from": 0.01,    "to": 192.17,  "rate": 0.19, "cumul": 0.00},
            {"name": "Basic",        "from": 192.18,  "to": 1165.92, "rate": 0.20, "cumul": 36.51},
            {"name": "Intermediate", "from": 1165.93, "to": 2591.00, "rate": 0.21, "cumul": 231.26},
            {"name": "Higher",       "from": 2591.01, "to": 5202.50, "rate": 0.42, "cumul": 530.53},
            {"name": "Advanced",     "from": 5202.51, "to": 9380.83, "rate": 0.45, "cumul": 1627.36},
            {"name": "Top",          "from": 9380.84, "to": None,    "rate": 0.48, "cumul": 3507.61},
        ],
    },
    TaxYear.Y2025_26: {
        "monthly_basic_ceiling": 3141.67,
        "monthly_higher_ceiling": 10428.33,
        "basic_rate": 0.20,
        "higher_rate": 0.40,
        "additional_rate": 0.45,
        "batch_annual": 5000.04,
        "scottish_bands": [
            {"name": "Starter",      "from": 0.01,    "to": 235.58,  "rate": 0.19, "cumul": 0.00},
            {"name": "Basic",        "from": 235.59,  "to": 1243.42, "rate": 0.20, "cumul": 44.76},
            {"name": "Intermediate", "from": 1243.43, "to": 2591.00, "rate": 0.21, "cumul": 246.33},
            {"name": "Higher",       "from": 2591.01, "to": 5202.50, "rate": 0.42, "cumul": 529.32},
            {"name": "Advanced",     "from": 5202.51, "to": 10428.33,"rate": 0.45, "cumul": 1626.15},
            {"name": "Top",          "from": 10428.34,"to": None,    "rate": 0.48, "cumul": 3977.77},
        ],
    },
    TaxYear.Y2026_27: {
        "monthly_basic_ceiling": 3141.67,
        "monthly_higher_ceiling": 10428.33,
        "basic_rate": 0.20,
        "higher_rate": 0.40,
        "additional_rate": 0.45,
        "batch_annual": 5000.04,
        "scottish_bands": [
            {"name": "Starter",      "from": 0.01,    "to": 330.58,  "rate": 0.19, "cumul": 0.00},
            {"name": "Basic",        "from": 330.59,  "to": 1413.00, "rate": 0.20, "cumul": 62.81},
            {"name": "Intermediate", "from": 1413.01, "to": 2591.00, "rate": 0.21, "cumul": 279.29},
            {"name": "Higher",       "from": 2591.01, "to": 5202.50, "rate": 0.42, "cumul": 526.67},
            {"name": "Advanced",     "from": 5202.51, "to": 10428.33,"rate": 0.45, "cumul": 1623.50},
            {"name": "Top",          "from": 10428.34,"to": None,    "rate": 0.48, "cumul": 3975.13},
        ],
    },
}

# Category remainder lookup tables
CAT_A_REMAINDERS = set(range(1, 501, 3))   # 1, 4, 7, 10...
CAT_B_REMAINDERS = set(range(2, 502, 3))   # 2, 5, 8, 11...
# Cat C = everything else (3, 6, 9, 12...)


# ---------------------------------------------------------------------------
# TAX CODE PARSING
# ---------------------------------------------------------------------------

def parse_tax_code(tax_code: str) -> dict:
    """
    Parse a tax code string into its components.
    Returns dict with keys: prefix, number, suffix, is_k, is_scottish,
    is_welsh, is_emergency, is_flat_rate, flat_rate, is_nt, is_0t
    """
    code = tax_code.strip().upper()
    result = {
        "prefix": None,
        "number": None,
        "suffix": None,
        "is_k": False,
        "is_scottish": False,
        "is_welsh": False,
        "is_emergency": False,
        "is_flat_rate": False,
        "flat_rate": None,
        "is_nt": False,
        "is_0t": False,
        "raw": tax_code,
    }

    # Flat rate codes
    if code in ("BR",):
        result["is_flat_rate"] = True
        result["flat_rate"] = 0.20
        return result
    if code in ("D0",):
        result["is_flat_rate"] = True
        result["flat_rate"] = 0.40
        return result
    if code in ("D1",):
        result["is_flat_rate"] = True
        result["flat_rate"] = 0.45
        return result
    if code == "NT":
        result["is_nt"] = True
        return result
    if code == "0T":
        result["is_0t"] = True
        return result

    # Scottish prefix
    if code.startswith("S"):
        result["is_scottish"] = True
        code = code[1:]

    # Welsh prefix
    if code.startswith("C"):
        result["is_welsh"] = True
        code = code[1:]

    # K code
    if code.startswith("K"):
        result["is_k"] = True
        code = code[1:]

    # Emergency suffix
    if code.endswith("X") or code.endswith("M1") or code.endswith("W1"):
        result["is_emergency"] = True
        if code.endswith("M1") or code.endswith("W1"):
            suffix = code[-2:]
            code = code[:-2]
        else:
            suffix = "X"
            code = code[:-1]
        result["suffix"] = suffix

    # Strip whitespace left by space-separated codes e.g. "K407 M1" -> "407 " -> "407"
    code = code.strip()

    # Extract suffix (L, M, N, T)
    # Must strip even if emergency suffix already found — e.g. "1257L M1" still has an L
    if code and code[-1] in ("L", "M", "N", "T"):
        if not result["suffix"]:
            result["suffix"] = code[-1]   # Only record it if we haven't already (M1/W1/X)
        code = code[:-1]                  # Always strip the letter so the number is clean

    # Extract number
    if code.isdigit():
        result["number"] = int(code)

    return result


# ---------------------------------------------------------------------------
# FREE PAY BATCHING METHOD
# ---------------------------------------------------------------------------

def calculate_free_pay(code_number: int, tax_period: int,
                       is_emergency: bool = False,
                       is_k_code: bool = False,
                       frequency: str = "monthly") -> Tuple[float, dict]:
    """
    Calculate cumulative free pay (or K addition) using the batching method.
    ALWAYS use this — never use simple (code × 10) ÷ 12.

    Returns (free_pay_amount, workings_dict)
    """
    period = 1 if is_emergency else tax_period
    batches = 0
    remainder = code_number

    # Count batches of 500
    while remainder > 500:
        remainder -= 500
        batches += 1

    # Determine category and remainder annual value
    if remainder in CAT_A_REMAINDERS:
        category = "A"
        remainder_annual = (remainder * 10) + 9.08
    elif remainder in CAT_B_REMAINDERS:
        category = "B"
        remainder_annual = (remainder * 10) + 9.04
    else:
        category = "C"
        remainder_annual = (remainder * 10) + 9.00

    # Annual value
    if frequency == "monthly":
        batch_annual = 5000.04
        periods_per_year = 12
    else:  # weekly
        batch_annual = 5000.32
        periods_per_year = 52

    batches_annual = batches * batch_annual
    total_annual = remainder_annual + batches_annual

    # Cumulative for period
    cumulative = (total_annual / periods_per_year) * period

    workings = {
        "code_number": code_number,
        "batches": batches,
        "remainder": remainder,
        "category": category,
        "remainder_annual": remainder_annual,
        "batches_annual": batches_annual,
        "total_annual": total_annual,
        "period": period,
        "cumulative": round(cumulative, 2),
    }

    return round(cumulative, 2), workings


# ---------------------------------------------------------------------------
# ENGLAND/WALES TAX BANDS
# ---------------------------------------------------------------------------

def apply_england_wales_bands(ytd_taxable_rounded: int,
                               config: dict) -> Tuple[float, List[dict]]:
    """
    Apply England/Wales tax bands to rounded YTD taxable pay.
    Returns (ytd_tax, bands_applied)
    """
    basic_ceil = config["monthly_basic_ceiling"]
    higher_ceil = config["monthly_higher_ceiling"]
    bands = []
    ytd_tax = 0.0

    if ytd_taxable_rounded <= 0:
        return 0.0, bands

    # Basic rate band
    basic_taxable = min(ytd_taxable_rounded, basic_ceil)
    basic_tax = round(basic_taxable * config["basic_rate"], 2)
    bands.append({
        "band": "Basic",
        "rate": config["basic_rate"],
        "taxable": basic_taxable,
        "tax": basic_tax,
    })
    ytd_tax += basic_tax

    if ytd_taxable_rounded > basic_ceil:
        # Higher rate band
        higher_taxable = min(ytd_taxable_rounded - basic_ceil,
                             higher_ceil - basic_ceil)
        higher_tax = round(higher_taxable * config["higher_rate"], 2)
        bands.append({
            "band": "Higher",
            "rate": config["higher_rate"],
            "taxable": higher_taxable,
            "tax": higher_tax,
        })
        ytd_tax += higher_tax

    if ytd_taxable_rounded > higher_ceil:
        # Additional rate band
        additional_taxable = ytd_taxable_rounded - higher_ceil
        additional_tax = round(additional_taxable * config["additional_rate"], 2)
        bands.append({
            "band": "Additional",
            "rate": config["additional_rate"],
            "taxable": additional_taxable,
            "tax": additional_tax,
        })
        ytd_tax += additional_tax

    return round(ytd_tax, 2), bands


# ---------------------------------------------------------------------------
# SCOTTISH TAX BANDS
# ---------------------------------------------------------------------------

def apply_scottish_bands(ytd_taxable_rounded: int,
                          config: dict) -> Tuple[float, List[dict]]:
    """
    Apply Scottish tax bands to rounded YTD taxable pay.
    Returns (ytd_tax, bands_applied)
    """
    bands_applied = []
    ytd_tax = 0.0

    if ytd_taxable_rounded <= 0:
        return 0.0, bands_applied

    scottish_bands = config["scottish_bands"]

    for band in scottish_bands:
        band_from = band["from"]
        band_to = band["to"]
        rate = band["rate"]
        cumul = band["cumul"]

        if ytd_taxable_rounded < band_from:
            break

        if band_to is None or ytd_taxable_rounded <= band_to:
            # Taxable falls in this band
            taxable_in_band = ytd_taxable_rounded - (band_from - 0.01)
            tax_in_band = round(taxable_in_band * rate, 2)
            bands_applied.append({
                "band": band["name"],
                "rate": rate,
                "taxable": taxable_in_band,
                "tax": tax_in_band,
            })
            ytd_tax = round(cumul + tax_in_band, 2)
            break
        else:
            # Full band used
            taxable_in_band = band_to - (band_from - 0.01)
            tax_in_band = round(taxable_in_band * rate, 2)
            bands_applied.append({
                "band": band["name"],
                "rate": rate,
                "taxable": taxable_in_band,
                "tax": tax_in_band,
            })

    ytd_tax = round(sum(b["tax"] for b in bands_applied), 2)
    return ytd_tax, bands_applied


# ---------------------------------------------------------------------------
# MAIN TAX CALCULATION
# ---------------------------------------------------------------------------

def calculate_tax(gross_for_tax: float,
                  ytd_gross_for_tax: float,
                  tax_code: str,
                  tax_period: int,
                  tax_year: TaxYear,
                  frequency: str = "monthly") -> TaxBreakdown:
    """
    Calculate income tax for a pay period.
    Returns full TaxBreakdown including drill-down workings.

    gross_for_tax: this period's gross for tax (built from pay lines)
    ytd_gross_for_tax: YTD gross for tax INCLUDING this period
    """
    parsed = parse_tax_code(tax_code)
    config = TAX_CONFIG[tax_year]

    # Guard against None tax_period
    if not tax_period:
        tax_period = 1

    # --- Flat rate codes ---
    if parsed["is_nt"]:
        return TaxBreakdown(
            tax_code=tax_code, is_k_code=False, is_emergency=False,
            is_scottish=False, free_pay_annual=0, free_pay_period=0,
            k_addition=None, ytd_gross_for_tax=ytd_gross_for_tax,
            ytd_taxable=0, ytd_taxable_rounded=0, bands_applied=[],
            ytd_tax_calculated=0, prior_period_tax=0, tax_this_period=0,
            cap_applied=False, cap_limit=None,
        )

    if parsed["is_flat_rate"]:
        tax = round(gross_for_tax * parsed["flat_rate"], 2)
        return TaxBreakdown(
            tax_code=tax_code, is_k_code=False, is_emergency=False,
            is_scottish=parsed["is_scottish"], free_pay_annual=0,
            free_pay_period=0, k_addition=None,
            ytd_gross_for_tax=ytd_gross_for_tax,
            ytd_taxable=gross_for_tax, ytd_taxable_rounded=int(gross_for_tax),
            bands_applied=[{"band": tax_code, "rate": parsed["flat_rate"],
                            "taxable": gross_for_tax, "tax": tax}],
            ytd_tax_calculated=tax, prior_period_tax=0,
            tax_this_period=tax, cap_applied=False, cap_limit=None,
        )

    if parsed["is_0t"]:
        # Zero allowance — tax from £0 using normal bands
        ytd_taxable_rounded = math.floor(ytd_gross_for_tax)
        if parsed["is_scottish"]:
            ytd_tax, bands = apply_scottish_bands(ytd_taxable_rounded, config)
        else:
            ytd_tax, bands = apply_england_wales_bands(ytd_taxable_rounded, config)

        prior_ytd = ytd_gross_for_tax - gross_for_tax
        prior_taxable_rounded = math.floor(prior_ytd)
        if parsed["is_scottish"]:
            prior_tax, _ = apply_scottish_bands(prior_taxable_rounded, config)
        else:
            prior_tax, _ = apply_england_wales_bands(prior_taxable_rounded, config)

        tax_this_period = round(ytd_tax - prior_tax, 2)
        return TaxBreakdown(
            tax_code=tax_code, is_k_code=False,
            is_emergency=parsed["is_emergency"],
            is_scottish=parsed["is_scottish"],
            free_pay_annual=0, free_pay_period=0, k_addition=None,
            ytd_gross_for_tax=ytd_gross_for_tax,
            ytd_taxable=ytd_gross_for_tax,
            ytd_taxable_rounded=ytd_taxable_rounded,
            bands_applied=bands, ytd_tax_calculated=ytd_tax,
            prior_period_tax=prior_tax, tax_this_period=tax_this_period,
            cap_applied=False, cap_limit=None,
        )

    # --- Standard codes with free pay or K addition ---
    code_number = parsed["number"]
    is_k = parsed["is_k"]
    is_emergency = parsed["is_emergency"]
    is_scottish = parsed["is_scottish"]

    # Guard: if code number could not be parsed, treat as 0T (no free pay)
    if code_number is None:
        ytd_taxable_rounded = math.floor(ytd_gross_for_tax)
        if is_scottish:
            ytd_tax, bands = apply_scottish_bands(ytd_taxable_rounded, config)
        else:
            ytd_tax, bands = apply_england_wales_bands(ytd_taxable_rounded, config)
        prior_ytd = ytd_gross_for_tax - gross_for_tax
        prior_taxable_rounded = math.floor(prior_ytd)
        if is_scottish:
            prior_tax, _ = apply_scottish_bands(prior_taxable_rounded, config)
        else:
            prior_tax, _ = apply_england_wales_bands(prior_taxable_rounded, config)
        tax_this_period = round(max(0, ytd_tax - prior_tax), 2)
        cap_limit = round(gross_for_tax * 0.50, 2)
        cap_applied = tax_this_period > cap_limit
        if cap_applied:
            tax_this_period = cap_limit
        return TaxBreakdown(
            tax_code=tax_code, is_k_code=False, is_emergency=is_emergency,
            is_scottish=is_scottish, free_pay_annual=0, free_pay_period=0,
            k_addition=None, ytd_gross_for_tax=ytd_gross_for_tax,
            ytd_taxable=ytd_gross_for_tax, ytd_taxable_rounded=ytd_taxable_rounded,
            bands_applied=bands, ytd_tax_calculated=ytd_tax,
            prior_period_tax=round(prior_tax, 2), tax_this_period=tax_this_period,
            cap_applied=cap_applied, cap_limit=cap_limit if cap_applied else None,
        )

    free_pay_period, workings = calculate_free_pay(
        code_number, tax_period, is_emergency, is_k, frequency
    )
    free_pay_annual = workings["total_annual"]

    if is_k:
        # K code: addition to gross for tax
        k_addition = free_pay_period
        ytd_taxable = ytd_gross_for_tax + k_addition
        # Prior period K addition
        prior_period = (tax_period - 1) if not is_emergency else 0
        if prior_period > 0:
            prior_k, _ = calculate_free_pay(
                code_number, prior_period, is_emergency, True, frequency
            )
        else:
            prior_k = 0.0
        prior_ytd_taxable = (ytd_gross_for_tax - gross_for_tax) + prior_k
    else:
        k_addition = None
        ytd_taxable = ytd_gross_for_tax - free_pay_period
        # Prior period free pay
        prior_period = (tax_period - 1) if not is_emergency else 0
        if prior_period > 0:
            prior_fp, _ = calculate_free_pay(
                code_number, prior_period, is_emergency, False, frequency
            )
        else:
            prior_fp = 0.0
        prior_ytd_gross = ytd_gross_for_tax - gross_for_tax
        prior_ytd_taxable = prior_ytd_gross - prior_fp

    # Round DOWN to nearest £1
    ytd_taxable_rounded = math.floor(ytd_taxable)
    prior_ytd_taxable_rounded = math.floor(prior_ytd_taxable)

    # Apply tax bands
    if is_scottish:
        ytd_tax, bands = apply_scottish_bands(ytd_taxable_rounded, config)
        prior_tax, _ = apply_scottish_bands(prior_ytd_taxable_rounded, config)
    else:
        ytd_tax, bands = apply_england_wales_bands(ytd_taxable_rounded, config)
        prior_tax, _ = apply_england_wales_bands(prior_ytd_taxable_rounded, config)

    tax_this_period = round(max(0, ytd_tax - prior_tax), 2)

    # 50% cap check
    cap_limit = round(gross_for_tax * 0.50, 2)
    cap_applied = tax_this_period > cap_limit
    if cap_applied:
        tax_this_period = cap_limit

    return TaxBreakdown(
        tax_code=tax_code,
        is_k_code=is_k,
        is_emergency=is_emergency,
        is_scottish=is_scottish,
        free_pay_annual=round(free_pay_annual, 2),
        free_pay_period=free_pay_period,
        k_addition=k_addition,
        ytd_gross_for_tax=ytd_gross_for_tax,
        ytd_taxable=round(ytd_taxable, 2),
        ytd_taxable_rounded=ytd_taxable_rounded,
        bands_applied=bands,
        ytd_tax_calculated=ytd_tax,
        prior_period_tax=round(prior_tax, 2),
        tax_this_period=tax_this_period,
        cap_applied=cap_applied,
        cap_limit=cap_limit if cap_applied else None,
    )
