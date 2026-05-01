"""
Wagestop — Pension Calculation Engine
Handles all pension types: RAS, NPA, Salary Sacrifice.
All bases: Qualifying Earnings, All Pay, Basic Pay, 85% of Earnings.
Includes salary sacrifice combined Er derivation (mandatory).
"""

from typing import Optional, Tuple
from .models import (
    PensionBreakdown, PensionType, PensionBasis, TaxYear, Flag, FlagSeverity
)


# ---------------------------------------------------------------------------
# TPR MINIMUMS
# ---------------------------------------------------------------------------

TPR_MINIMUMS = {
    PensionBasis.QUALIFYING_EARNINGS: {
        "total": 0.08, "er_min": 0.03, "ee_min": 0.05
    },
    PensionBasis.BASIC_PAY: {
        "total": 0.09, "er_min": 0.04, "ee_min": 0.05
    },
    PensionBasis.ALL_PAY: {
        "total": 0.07, "er_min": 0.03, "ee_min": 0.04
    },
    PensionBasis.EARNINGS_85: {
        "total": 0.08, "er_min": 0.03, "ee_min": 0.05
    },
}

# Monthly QE thresholds 2025/26
QE_LEL_MONTHLY = 520.00
QE_UEL_MONTHLY = 4189.00
QE_LEL_WEEKLY  = 120.00
QE_UEL_WEEKLY  = 967.00

# Provider restrictions
PROVIDER_ALLOWED_TYPES = {
    "nest":              [PensionType.RAS, PensionType.SALARY_SACRIFICE],
    "now pensions":      [PensionType.NPA, PensionType.SALARY_SACRIFICE],
    "smart pension":     [PensionType.NPA, PensionType.SALARY_SACRIFICE],
    "smart pensions":    [PensionType.NPA, PensionType.SALARY_SACRIFICE],
    "the people's pension": [PensionType.RAS, PensionType.NPA, PensionType.SALARY_SACRIFICE],
    "peoples pension":   [PensionType.RAS, PensionType.NPA, PensionType.SALARY_SACRIFICE],
    "aviva":             [PensionType.RAS, PensionType.NPA, PensionType.SALARY_SACRIFICE],
    "royal london":      [PensionType.RAS, PensionType.NPA, PensionType.SALARY_SACRIFICE],
    "aegon":             [PensionType.RAS, PensionType.NPA, PensionType.SALARY_SACRIFICE],
    "cushon":            [PensionType.RAS, PensionType.NPA, PensionType.SALARY_SACRIFICE],
    "true potential":    [PensionType.RAS, PensionType.NPA, PensionType.SALARY_SACRIFICE],
}

COMMON_PENSION_RATES = [
    0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12, 0.15, 0.20
]
RATE_TOLERANCE = 0.10   # £0.10 tolerance when matching rates


# ---------------------------------------------------------------------------
# QE PENSIONABLE PAY (P9)
# ---------------------------------------------------------------------------

def calculate_qe_pensionable(ni_able_earnings: float,
                              frequency: str = "monthly") -> float:
    """
    QE pensionable pay = min(NI-able earnings, UEL) - LEL
    Uses NI-able earnings (not gross for tax).
    Non-NIC payments already excluded before this point.
    """
    lel = QE_LEL_MONTHLY if frequency == "monthly" else QE_LEL_WEEKLY
    uel = QE_UEL_MONTHLY if frequency == "monthly" else QE_UEL_WEEKLY
    return round(max(0, min(ni_able_earnings, uel) - lel), 2)


# ---------------------------------------------------------------------------
# PENSION TYPE IDENTIFICATION
# ---------------------------------------------------------------------------

def identify_pension_type(gross_for_tax_changed: bool,
                           gross_for_ni_changed: bool,
                           has_sacrifice_line: bool) -> PensionType:
    """
    Identify pension type from gross pay changes.
    - RAS: neither gross changes
    - NPA: gross for tax reduces, NI unchanged
    - Salary Sacrifice: both reduce (sacrifice line present)
    """
    if has_sacrifice_line or (gross_for_tax_changed and gross_for_ni_changed):
        return PensionType.SALARY_SACRIFICE
    elif gross_for_tax_changed and not gross_for_ni_changed:
        return PensionType.NPA
    else:
        return PensionType.RAS


# ---------------------------------------------------------------------------
# SALARY SACRIFICE — DERIVE TRUE ER (MANDATORY — P3/C4)
# ---------------------------------------------------------------------------

def derive_true_er(combined_er_shown: float,
                   ee_sacrifice: float) -> float:
    """
    MANDATORY for Sage 50 Desktop and BrightPay salary sacrifice.
    These show COMBINED Er = true Er + Ee sacrifice.
    True Er = combined shown - Ee sacrifice.
    ALWAYS call this before stating any Er rate.
    """
    return round(combined_er_shown - ee_sacrifice, 2)


def is_combined_er_software(software: Optional[str]) -> bool:
    """
    Returns True if software shows combined Er pension (true Er + sacrifice).
    Sage 50 Desktop and BrightPay both show combined.
    """
    if not software:
        return False
    s = software.lower()
    return "sage" in s or "brightpay" in s


# ---------------------------------------------------------------------------
# PENSION BASIS DERIVATION
# ---------------------------------------------------------------------------

def derive_pension_basis(er_contribution: float,
                          pensionable_pay_gross: float,
                          ni_able_earnings: float,
                          frequency: str = "monthly") -> Tuple[PensionBasis, float, float]:
    """
    Derive pension basis from Er contribution and pay figures.
    Returns (basis, er_rate, pensionable_pay_used)

    Tests in order:
    1. QE: er / (min(ni_able, UEL) - LEL) = clean rate
    2. All Pay: er / gross = clean rate
    3. 85%: er / (gross * 0.85) = clean rate
    4. Basic Pay: same as All Pay (differentiated by contract, not calculation)
    """
    # Test QE
    qe_pay = calculate_qe_pensionable(ni_able_earnings, frequency)
    if qe_pay > 0:
        for rate in COMMON_PENSION_RATES:
            if abs(er_contribution - round(qe_pay * rate, 2)) <= RATE_TOLERANCE:
                return PensionBasis.QUALIFYING_EARNINGS, rate, qe_pay

    # Test All Pay
    if pensionable_pay_gross > 0:
        for rate in COMMON_PENSION_RATES:
            if abs(er_contribution - round(pensionable_pay_gross * rate, 2)) <= RATE_TOLERANCE:
                return PensionBasis.ALL_PAY, rate, pensionable_pay_gross

    # Test 85% of Earnings
    pay_85 = round(pensionable_pay_gross * 0.85, 2)
    if pay_85 > 0:
        for rate in COMMON_PENSION_RATES:
            if abs(er_contribution - round(pay_85 * rate, 2)) <= RATE_TOLERANCE:
                return PensionBasis.EARNINGS_85, rate, pay_85

    return PensionBasis.UNKNOWN, 0.0, pensionable_pay_gross


# ---------------------------------------------------------------------------
# PROVIDER COMPATIBILITY CHECK
# ---------------------------------------------------------------------------

def check_provider_compatibility(provider: Optional[str],
                                  pension_type: PensionType) -> Optional[Flag]:
    """
    Check if pension type is allowed for the given provider.
    Returns a Flag if incompatible, None if compatible or provider unknown.
    """
    if not provider:
        return None

    provider_key = provider.lower().strip()
    allowed = PROVIDER_ALLOWED_TYPES.get(provider_key)

    if allowed and pension_type not in allowed:
        return Flag(
            severity=FlagSeverity.ERROR,
            element_code="PENSION",
            code="WRONG_PENSION_BASIS",
            message="Pension deducted on wrong tax basis",
        )
    return None


# ---------------------------------------------------------------------------
# MAIN PENSION CALCULATION
# ---------------------------------------------------------------------------

def calculate_pension(gross_for_tax: float,
                       gross_for_ni: float,
                       ni_able_earnings: float,
                       ee_contribution_shown: float,
                       er_contribution_shown: float,
                       has_sacrifice_line: bool,
                       sacrifice_amount: float,
                       gross_for_tax_changed: bool,
                       gross_for_ni_changed: bool,
                       software: Optional[str],
                       provider: Optional[str],
                       frequency: str = "monthly") -> Tuple[PensionBreakdown, list]:
    """
    Main pension validation.
    Returns (PensionBreakdown, list_of_flags)

    Steps (mandatory order per C4/P3):
    1. Identify pension type
    2. If salary sacrifice + combined Er software: derive true Er
    3. Derive pension basis from true Er
    4. Calculate expected contributions
    5. Check TPR minimums
    6. Check provider compatibility
    """
    flags = []

    # Step 1 — Identify pension type
    pension_type = identify_pension_type(
        gross_for_tax_changed, gross_for_ni_changed, has_sacrifice_line
    )

    # Step 2 — Derive true Er for salary sacrifice on combined-display software
    if pension_type == PensionType.SALARY_SACRIFICE and is_combined_er_software(software):
        true_er = derive_true_er(er_contribution_shown, sacrifice_amount)
        combined_er_shown = er_contribution_shown
    else:
        true_er = er_contribution_shown
        combined_er_shown = None

    # Step 3 — Derive pension basis
    # Use notional (pre-sacrifice) pay for salary sacrifice
    notional_gross = gross_for_tax + sacrifice_amount if pension_type == PensionType.SALARY_SACRIFICE else gross_for_tax

    basis, er_rate, pensionable_pay = derive_pension_basis(
        true_er, notional_gross, ni_able_earnings, frequency
    )

    # Step 4 — Calculate expected contributions
    if basis == PensionBasis.QUALIFYING_EARNINGS:
        pensionable_pay = calculate_qe_pensionable(ni_able_earnings, frequency)

    expected_er = round(pensionable_pay * er_rate, 2) if er_rate else true_er

    # For RAS: payslip shows 80% of the gross contribution (provider reclaims 20% from HMRC).
    # Back-calculate ee_rate from the shown net amount, then round to 4dp to avoid
    # floating point errors from payroll software rounding causing false TPR failures.
    # e.g. £2563.33 × 5% × 80% = £102.5332 → shown as £102.53 → raw back-calc = 0.049998
    if pension_type == PensionType.RAS:
        ee_rate = round((ee_contribution_shown / pensionable_pay / 0.80), 4) if pensionable_pay > 0 else 0
        ee_gross_contribution = round(pensionable_pay * ee_rate, 2)
        ee_expected_shown = round(ee_gross_contribution * 0.80, 2)
    else:
        ee_rate = round((ee_contribution_shown / pensionable_pay), 4) if pensionable_pay > 0 else 0
        ee_gross_contribution = ee_contribution_shown
        ee_expected_shown = ee_contribution_shown

    # Step 5 — TPR minimum check
    tpr = TPR_MINIMUMS.get(basis, TPR_MINIMUMS[PensionBasis.ALL_PAY])
    tpr_total_min = tpr["total"]
    tpr_er_min = tpr["er_min"]
    tpr_ee_min = tpr["total"] - er_rate if er_rate else tpr["ee_min"]

    total_rate = er_rate + ee_rate if er_rate else 0
    tpr_total_met = total_rate >= tpr_total_min
    tpr_er_met = er_rate >= tpr_er_min if er_rate else False
    tpr_ee_met = ee_rate >= tpr_ee_min

    if not tpr_total_met or not tpr_er_met:
        flags.append(Flag(
            severity=FlagSeverity.ERROR,
            element_code="PENSION_ER",
            code="TPR_MINIMUM_NOT_MET",
            message="TPR MINIMUM NOT MET",
            expected=tpr_total_min,
            actual=total_rate,
        ))

    if not tpr_ee_met:
        flags.append(Flag(
            severity=FlagSeverity.ERROR,
            element_code="PENSION_EE",
            code="TPR_EE_MINIMUM_NOT_MET",
            message=(
                f"Your employee pension contribution of {ee_rate*100:.1f}% is below "
                f"the minimum required by The Pensions Regulator of {tpr_ee_min*100:.1f}%. "
                f"Please check with your employer."
            ),
            expected=tpr_ee_min,
            actual=ee_rate,
        ))

    # Step 6 — Provider compatibility
    provider_flag = check_provider_compatibility(provider, pension_type)
    if provider_flag:
        flags.append(provider_flag)

    breakdown = PensionBreakdown(
        pension_type=pension_type,
        pension_basis=basis,
        provider=provider,
        pensionable_pay=pensionable_pay,
        ee_contribution_expected=ee_expected_shown,
        er_contribution_expected=expected_er,
        er_true_contribution=true_er,
        combined_er_shown=combined_er_shown,
        tpr_total_min_pct=tpr_total_min,
        tpr_er_min_pct=tpr_er_min,
        tpr_ee_min_pct=tpr_ee_min,
        tpr_total_met=tpr_total_met,
        tpr_er_met=tpr_er_met,
        tpr_ee_met=tpr_ee_met,
    )

    return breakdown, flags
