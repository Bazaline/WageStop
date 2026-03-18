"""
Wagestop — Student Loan Calculation Engine
Handles Plans 1, 2, 4, 5 and Postgraduate (PGL).
Calculated on NI-able earnings — not gross for tax.
Always round DOWN to nearest £1. Non-cumulative per period.
"""

import math
from typing import Optional
from .models import TaxYear, Flag, FlagSeverity


# ---------------------------------------------------------------------------
# THRESHOLDS (Source: HMRC / GOV.UK)
# ---------------------------------------------------------------------------

STUDENT_LOAN_THRESHOLDS = {
    TaxYear.Y2024_25: {
        "Plan1": {"monthly": 2082.00,  "weekly": 480.00,  "rate": 0.09, "active": True},
        "Plan2": {"monthly": 2274.00,  "weekly": 524.00,  "rate": 0.09, "active": True},
        "Plan4": {"monthly": 2616.00,  "weekly": 603.00,  "rate": 0.09, "active": True},
        "Plan5": {"monthly": None,     "weekly": None,    "rate": 0.09, "active": False},  # No deductions until Apr 2026
        "PGL":   {"monthly": 1750.00,  "weekly": 403.00,  "rate": 0.06, "active": True},
    },
    TaxYear.Y2025_26: {
        "Plan1": {"monthly": 2172.00,  "weekly": 501.00,  "rate": 0.09, "active": True},
        "Plan2": {"monthly": 2372.00,  "weekly": 547.00,  "rate": 0.09, "active": True},
        "Plan4": {"monthly": 2728.00,  "weekly": 629.00,  "rate": 0.09, "active": True},
        "Plan5": {"monthly": 2083.00,  "weekly": 480.00,  "rate": 0.09, "active": False},  # No deductions until Apr 2026
        "PGL":   {"monthly": 1750.00,  "weekly": 403.00,  "rate": 0.06, "active": True},
    },
    TaxYear.Y2026_27: {
        "Plan1": {"monthly": 2241.00,  "weekly": 517.00,  "rate": 0.09, "active": True},
        "Plan2": {"monthly": 2448.00,  "weekly": 565.00,  "rate": 0.09, "active": True},
        "Plan4": {"monthly": 2816.00,  "weekly": 649.00,  "rate": 0.09, "active": True},
        "Plan5": {"monthly": 2083.00,  "weekly": 480.00,  "rate": 0.09, "active": True},   # Active from April 2026
        "PGL":   {"monthly": 1750.00,  "weekly": 403.00,  "rate": 0.06, "active": True},
    },
}


# ---------------------------------------------------------------------------
# STUDENT LOAN CALCULATION (P10)
# ---------------------------------------------------------------------------

def calculate_student_loan(ni_able_earnings: float,
                            plan: str,
                            tax_year: TaxYear,
                            frequency: str = "monthly") -> tuple[float, Optional[Flag]]:
    """
    Calculate student loan deduction for a pay period.
    
    CRITICAL: Uses NI-able earnings — NOT gross for tax (P10).
    Non-NIC payments (Tronc, expenses) must already be excluded 
    from ni_able_earnings before calling this function.
    
    Returns (deduction_amount, flag_if_any)
    """
    plans = STUDENT_LOAN_THRESHOLDS.get(tax_year, {})
    plan_data = plans.get(plan)
    
    if not plan_data:
        return 0.0, Flag(
            severity=FlagSeverity.WARNING,
            element_code="STUDENT_LOAN",
            code="UNKNOWN_PLAN",
            message=f"Student loan plan '{plan}' not recognised. Please check your loan plan.",
        )
    
    # Plan 5 not active until 2026/27
    if not plan_data["active"]:
        return 0.0, Flag(
            severity=FlagSeverity.INFO,
            element_code="STUDENT_LOAN",
            code="PLAN_NOT_YET_ACTIVE",
            message=(
                f"Student loan Plan 5 deductions do not start until April 2026. "
                f"No deduction should be taken in {tax_year.value}."
            ),
        )
    
    threshold = plan_data[frequency]
    rate = plan_data["rate"]
    
    if ni_able_earnings <= threshold:
        return 0.0, None
    
    # Calculate: (NI-able earnings - threshold) × rate, round DOWN to £1
    excess = ni_able_earnings - threshold
    deduction = math.floor(excess * rate)
    
    return float(deduction), None


def identify_student_loan_plan(ni_able_earnings: float,
                                deduction_shown: float,
                                tax_year: TaxYear,
                                frequency: str = "monthly") -> Optional[str]:
    """
    Attempt to identify which student loan plan is in use
    by testing deduction against all active plans.
    Returns plan name if match found, None if unidentifiable.
    """
    plans = STUDENT_LOAN_THRESHOLDS.get(tax_year, {})
    
    for plan_name, plan_data in plans.items():
        if not plan_data["active"]:
            continue
        
        threshold = plan_data[frequency]
        if threshold is None or ni_able_earnings <= threshold:
            continue
        
        expected = math.floor((ni_able_earnings - threshold) * plan_data["rate"])
        if abs(expected - deduction_shown) <= 1:  # £1 tolerance for rounding
            return plan_name
    
    return None


def validate_student_loan(ni_able_earnings: float,
                           deduction_shown: float,
                           plan: Optional[str],
                           tax_year: TaxYear,
                           frequency: str = "monthly") -> list[Flag]:
    """
    Validate student loan deduction shown on payslip.
    If plan is unknown, attempt to identify it.
    Returns list of flags.
    """
    flags = []
    
    # If no plan specified, try to identify from deduction
    if not plan:
        identified = identify_student_loan_plan(
            ni_able_earnings, deduction_shown, tax_year, frequency
        )
        if identified:
            flags.append(Flag(
                severity=FlagSeverity.INFO,
                element_code="STUDENT_LOAN",
                code="PLAN_IDENTIFIED",
                message=f"Based on your deduction, this appears to be a {identified} student loan.",
            ))
            plan = identified
        else:
            flags.append(Flag(
                severity=FlagSeverity.WARNING,
                element_code="STUDENT_LOAN",
                code="PLAN_UNIDENTIFIABLE",
                message=(
                    "We couldn't identify your student loan plan from the deduction shown. "
                    "Please check your student loan plan type with the Student Loans Company."
                ),
            ))
            return flags
    
    # Calculate expected deduction
    expected, plan_flag = calculate_student_loan(
        ni_able_earnings, plan, tax_year, frequency
    )
    
    if plan_flag:
        flags.append(plan_flag)
        return flags
    
    # Compare to payslip
    variance = abs(expected - deduction_shown)
    if variance > 1:  # Over £1 variance
        flags.append(Flag(
            severity=FlagSeverity.ERROR,
            element_code="STUDENT_LOAN",
            code="STUDENT_LOAN_DISCREPANCY",
            message=(
                f"Student loan discrepancy — expected £{expected:.2f} "
                f"({plan}), payslip shows £{deduction_shown:.2f} "
                f"(variance £{variance:.2f})."
            ),
            expected=expected,
            actual=deduction_shown,
            variance=variance,
        ))
    
    return flags
