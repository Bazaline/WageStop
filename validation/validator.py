"""
Wagestop — Main Validation Orchestrator
Coordinates tax, NI, and pension engines.
Builds gross figures from pay lines (never reads summary figures).
Applies all flags in correct sequence.
"""

from typing import List, Optional
from datetime import datetime, date

from .models import (
    PayslipInput, ValidationResult, PayLine, Flag, FlagSeverity,
    PensionType, TaxYear, PayFrequency
)
from .tax import calculate_tax, parse_tax_code
from .ni import calculate_ni
from .pension import calculate_pension
from .student_loan import validate_student_loan, identify_student_loan_plan
from .special_elements import scan_special_elements
from .statutory_pay import validate_stat_pay_pension

# ---------------------------------------------------------------------------
# TOLERANCE LEVELS (P7 — strict)
# ---------------------------------------------------------------------------
TAX_TOLERANCE  = 0.05
NI_TOLERANCE   = 0.02


# ---------------------------------------------------------------------------
# TAX YEAR DETECTION
# ---------------------------------------------------------------------------

def detect_tax_year(payment_date_str: str) -> TaxYear:
    """Determine tax year from payment date"""
    try:
        d = datetime.strptime(payment_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return TaxYear.Y2025_26

    if date(2024, 4, 6) <= d <= date(2025, 4, 5):
        return TaxYear.Y2024_25
    elif date(2025, 4, 6) <= d <= date(2026, 4, 5):
        return TaxYear.Y2025_26
    elif date(2026, 4, 6) <= d <= date(2027, 4, 5):
        return TaxYear.Y2026_27
    return TaxYear.Y2025_26


def detect_tax_period(payment_date_str: str) -> int:
    """Determine tax month (1-12) from payment date"""
    try:
        d = datetime.strptime(payment_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return 1

    # Simpler approach: calculate directly
    if d.month > 3:
        # April to December
        month_offset = d.month - 4
        if d.day >= 6:
            return month_offset + 1
        else:
            return max(1, month_offset)
    else:
        # January to March
        if d.month == 1:
            return 10 if d.day >= 6 else 9
        elif d.month == 2:
            return 11 if d.day >= 6 else 10
        elif d.month == 3:
            return 12 if d.day >= 6 else 11
    return 1


def detect_tax_week(payment_date_str: str) -> int:
    """
    Determine tax week (1-53) from payment date.
    Tax week 1 starts April 6.
    """
    try:
        d = datetime.strptime(payment_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return 1

    # Find the start of the tax year (April 6)
    if d.month > 4 or (d.month == 4 and d.day >= 6):
        tax_year_start = date(d.year, 4, 6)
    elif d.month == 4 and d.day < 6:
        tax_year_start = date(d.year - 1, 4, 6)
    else:
        tax_year_start = date(d.year - 1, 4, 6)

    days_elapsed = (d - tax_year_start).days
    week = (days_elapsed // 7) + 1
    return max(1, min(week, 53))


# ---------------------------------------------------------------------------
# GROSS BUILDING (STEP 0 — never read summary figures)
# ---------------------------------------------------------------------------

# Tax treatment by element code
TAXABLE_ELEMENTS = {
    "A1","A2","A3","A4","A5","A6","A7","A8","A9","A10",
    "A12","A14","A15","A16","A17","A18","A19","A16_OR_A17",
    "C3",   # RAS pension — gross unchanged
    "D1","D2","D3",  # BIK — taxable but not in net pay
}
NON_TAXABLE_ELEMENTS = {"A11","A13"}
NI_ABLE_ELEMENTS = {
    "A1","A2","A3","A4","A5","A6","A7","A8","A9","A10",
    "A14","A16","A17","A18","A19","A16_OR_A17",
}
NON_NI_ELEMENTS = {"A11","A12","A13","A15"}   # A12 Tronc flagged separately
REDUCES_TAX_GROSS = {"C4","C5","B5"}    # NPA pension, salary sacrifice, other sacrifice
REDUCES_NI_GROSS  = {"C5","B5"}         # Salary sacrifice only

STAT_PAY_ELEMENTS = {"A16","A17","A16_OR_A17"}  # SMP/SPP — pension rules apply


def build_gross_figures(pay_lines: List[PayLine]) -> dict:
    """
    Build gross for tax, gross for NI, and pensionable pay
    independently from individual pay lines.
    NEVER reads summary figures.
    """
    gross_for_tax = 0.0
    gross_for_ni  = 0.0
    total_gross   = 0.0
    sacrifice_amount = 0.0
    has_sacrifice_line = False
    has_stat_pay = False
    stat_pay_amount = 0.0
    bik_amount = 0.0
    has_b5_non_pension = False

    for line in pay_lines:
        code = line.element_code
        amount = line.amount

        # Total gross (all payments)
        if not code.startswith("B") and not code.startswith("C") \
                and not code.startswith("D") and not code.startswith("E"):
            if amount > 0:
                total_gross += amount

        # BIK — taxable but not in net pay
        if code in ("D1","D2","D3"):
            bik_amount += amount
            gross_for_tax += amount
            continue

        # Gross for tax
        if code in TAXABLE_ELEMENTS and code not in ("D1","D2","D3"):
            gross_for_tax += amount

        # Items that reduce gross for tax (NPA pension, salary sacrifice)
        if code in REDUCES_TAX_GROSS:
            if code == "B5":
                # Non-pension salary sacrifice
                has_b5_non_pension = True
                sacrifice_amount += abs(amount)
            elif code == "C5":
                # Pension salary sacrifice
                has_sacrifice_line = True
                sacrifice_amount += abs(amount)
            gross_for_tax -= abs(amount)

        # Gross for NI
        if code in NI_ABLE_ELEMENTS:
            gross_for_ni += amount
        if code in REDUCES_NI_GROSS:
            gross_for_ni -= abs(amount)

        # Stat pay tracking
        if code in STAT_PAY_ELEMENTS:
            has_stat_pay = True
            stat_pay_amount += amount

    # NPA pension reduces gross for tax only (already handled above via C4)

    return {
        "gross_for_tax": round(gross_for_tax, 2),
        "gross_for_ni": round(gross_for_ni, 2),
        "total_gross": round(total_gross, 2),
        "sacrifice_amount": round(sacrifice_amount, 2),
        "has_sacrifice_line": has_sacrifice_line,
        "has_stat_pay": has_stat_pay,
        "stat_pay_amount": round(stat_pay_amount, 2),
        "bik_amount": round(bik_amount, 2),
        "has_b5_non_pension": has_b5_non_pension,
    }


# ---------------------------------------------------------------------------
# FREQUENCY CONFLICT CHECK
# ---------------------------------------------------------------------------

def check_frequency_conflict(user_frequency: PayFrequency,
                               payslip_frequency: str) -> Optional[Flag]:
    """Flag if user-stated frequency differs from payslip frequency"""
    if user_frequency == PayFrequency.UNKNOWN:
        return None

    payslip_freq = PayFrequency.MONTHLY if payslip_frequency == "monthly" \
        else PayFrequency.WEEKLY

    if user_frequency != payslip_freq:
        user_label = "monthly" if user_frequency == PayFrequency.MONTHLY else "weekly"
        payslip_label = "weekly" if user_frequency == PayFrequency.MONTHLY else "monthly"
        return Flag(
            severity=FlagSeverity.WARNING,
            element_code="FREQUENCY",
            code="FREQUENCY_MISMATCH",
            message=(
                f"You told us you are paid {user_label} but your payslip shows a "
                f"{payslip_label} pay period. We have used your payslip frequency "
                f"for this analysis. Please check this is correct."
            ),
        )
    return None


# ---------------------------------------------------------------------------
# MAIN VALIDATOR
# ---------------------------------------------------------------------------

def validate_payslip(payslip: PayslipInput) -> ValidationResult:
    """
    Main validation function.
    Returns complete ValidationResult with all calculations and flags.
    """
    flags: List[Flag] = []

    # --- Determine tax year and period ---
    tax_year = detect_tax_year(payslip.payment_date)
    frequency = payslip.pay_frequency.value \
        if payslip.pay_frequency != PayFrequency.UNKNOWN else "monthly"

    # Detect period number based on frequency
    if payslip.tax_period:
        tax_period = payslip.tax_period
    elif frequency == "weekly":
        tax_period = detect_tax_week(payslip.payment_date)
    else:
        tax_period = detect_tax_period(payslip.payment_date)

    # --- Frequency conflict check ---
    freq_flag = check_frequency_conflict(
        payslip.user_answers.pay_frequency, frequency
    )
    if freq_flag:
        flags.append(freq_flag)

    # --- STEP 0: Build gross figures from pay lines ---
    gross = build_gross_figures(payslip.pay_lines)

    gross_for_tax = gross["gross_for_tax"]
    gross_for_ni  = gross["gross_for_ni"]
    sacrifice_amt = gross["sacrifice_amount"]
    has_sacrifice = gross["has_sacrifice_line"]

    # --- SPECIAL ELEMENTS (Tronc, BIK, Redundancy, PILON) ---
    special, special_flags = scan_special_elements(
        payslip.pay_lines, gross_for_tax, gross_for_ni
    )
    flags.extend(special_flags)

    # YTD gross for tax
    # Emergency/non-cumulative codes (M1/W1/X): ALWAYS use current period only.
    # The payslip YTD will be the full year-to-date which is irrelevant for M1/W1.
    # Cumulative codes: use payslip YTD if available, otherwise current period.
    _parsed_code = parse_tax_code(payslip.tax_code)
    _is_emergency = _parsed_code.get("is_emergency", False)

    if _is_emergency:
        # Non-cumulative — calculate on this period's gross only
        ytd_gross_for_tax = gross_for_tax
    elif payslip.ytd.ytd_gross_for_tax:
        ytd_gross_for_tax = payslip.ytd.ytd_gross_for_tax
    else:
        # No YTD — treat as period 1
        ytd_gross_for_tax = gross_for_tax
        if tax_period and tax_period > 1:
            flags.append(Flag(
                severity=FlagSeverity.WARNING,
                element_code="TAX",
                code="NO_YTD_DATA",
                message=(
                    "No year-to-date figures were found on your payslip. "
                    "We've calculated tax on this period only — for a fully "
                    "accurate cumulative result, please provide a payslip "
                    "that includes YTD totals."
                ),
            ))

    # --- TAX CALCULATION ---
    tax_breakdown = calculate_tax(
        gross_for_tax=gross_for_tax,
        ytd_gross_for_tax=ytd_gross_for_tax,
        tax_code=payslip.tax_code,
        tax_period=tax_period,
        tax_year=tax_year,
        frequency=frequency,
    )
    tax_expected = tax_breakdown.tax_this_period

    # Tax variance check
    tax_paid = payslip.summary.tax_paid or 0.0
    tax_variance = round(abs(tax_expected - tax_paid), 2)
    if tax_variance > TAX_TOLERANCE:
        flags.append(Flag(
            severity=FlagSeverity.ERROR,
            element_code="TAX",
            code="TAX_DISCREPANCY",
            message=(
                f"TAX DISCREPANCY — Expected £{tax_expected:.2f}, "
                f"payslip shows £{tax_paid:.2f} "
                f"(variance £{tax_variance:.2f})"
            ),
            expected=tax_expected,
            actual=tax_paid,
            variance=tax_variance,
        ))

    # --- NI CALCULATION ---
    ni_breakdown = calculate_ni(
        gross_for_ni=gross_for_ni,
        ni_category=payslip.ni_category,
        tax_year=tax_year,
        frequency=frequency,
    )
    ee_ni_expected = ni_breakdown.ee_ni_calculated
    er_ni_expected = ni_breakdown.er_ni_calculated

    # NI variance check
    ni_paid = payslip.summary.ni_paid or 0.0
    ee_ni_variance = round(abs(ee_ni_expected - ni_paid), 2)

    # Sage UEL display: payslip shows £4,189 for Earnings for NI as a display feature.
    # When this is present, suppress any NI discrepancy error — the info flag is enough.
    if ni_breakdown.sage_uel_display:
        flags.append(Flag(
            severity=FlagSeverity.INFO,
            element_code="NI",
            code="SAGE_UEL_DISPLAY",
            message=(
                "Your payslip shows Earnings for NI as £4,189.00 (the Upper Earnings "
                "Limit). This is a display feature — your actual NI has been correctly "
                "calculated on your full earnings above the UEL."
            ),
        ))
    elif ee_ni_variance > NI_TOLERANCE:
        flags.append(Flag(
            severity=FlagSeverity.ERROR,
            element_code="NI",
            code="NI_DISCREPANCY",
            message=(
                f"NI DISCREPANCY — Expected £{ee_ni_expected:.2f}, "
                f"payslip shows £{ni_paid:.2f} "
                f"(variance £{ee_ni_variance:.2f})"
            ),
            expected=ee_ni_expected,
            actual=ni_paid,
            variance=ee_ni_variance,
        ))

    # --- PENSION CALCULATION ---
    pension_breakdown = None
    pension_flags = []

    # --- B5 AS PENSION SACRIFICE DETECTION ---
    # When a salary sacrifice (B5) exists but there is no explicit employee pension
    # line (C3/C4/C5), and an employer pension (E3) is present, the B5 is acting
    # as the employee's pension sacrifice contribution.
    has_pension_line = any(
        l.element_code in ("C3", "C4", "C5", "C6") for l in payslip.pay_lines
    )
    has_er_pension_line = any(
        l.element_code == "E3" for l in payslip.pay_lines
    )
    b5_is_pension_sacrifice = (
        gross["has_b5_non_pension"]
        and sacrifice_amt > 0
        and not has_pension_line
        and has_er_pension_line
    )

    # Resolve effective ee/er pension figures
    if b5_is_pension_sacrifice:
        # B5 IS the employee pension — treat as salary sacrifice
        effective_ee_pension = sacrifice_amt
        effective_er_pension = payslip.pension.er_contribution_shown or 0.0
        # Also accept from E3 line directly if pension dict is empty
        if effective_er_pension == 0.0:
            for l in payslip.pay_lines:
                if l.element_code == "E3":
                    effective_er_pension += abs(l.amount)
        effective_has_sacrifice = True
    else:
        effective_ee_pension = payslip.pension.ee_contribution_shown or 0.0
        effective_er_pension = payslip.pension.er_contribution_shown or 0.0
        # Also resolve E3 if pension dict is empty
        if effective_er_pension == 0.0:
            for l in payslip.pay_lines:
                if l.element_code == "E3":
                    effective_er_pension += abs(l.amount)
        effective_has_sacrifice = has_sacrifice

    # Determine if parental stat pay is present (A16/A17 — not SSP/A18)
    has_parental_stat_pay = any(
        l.element_code in ("A16", "A17", "A16_OR_A17") for l in payslip.pay_lines
    )

    if effective_er_pension > 0 or effective_ee_pension > 0:

        # When parental stat pay is present alongside pension:
        # We cannot fully validate employer pension without pre-leave salary data.
        # Skip normal pension validation — Stage 2 will handle it.
        if has_parental_stat_pay:
            # Still run pension calculation for display purposes only
            gross_for_tax_changed = sacrifice_amt > 0 or any(
                line.element_code == "C4" for line in payslip.pay_lines
            )
            gross_for_ni_changed = effective_has_sacrifice

            pension_breakdown, _pension_flags = calculate_pension(
                gross_for_tax=gross_for_tax,
                gross_for_ni=gross_for_ni,
                ni_able_earnings=gross_for_ni,
                ee_contribution_shown=effective_ee_pension,
                er_contribution_shown=effective_er_pension,
                has_sacrifice_line=effective_has_sacrifice,
                sacrifice_amount=sacrifice_amt,
                gross_for_tax_changed=gross_for_tax_changed,
                gross_for_ni_changed=gross_for_ni_changed,
                software=payslip.software,
                provider=payslip.pension.provider or payslip.user_answers.pension_provider,
                frequency=frequency,
            )
            # Suppress pension error/warning flags — we can't validate without pre-leave data
            # Only keep provider compatibility error if present
            for f in _pension_flags:
                if f.code == "WRONG_PENSION_BASIS":
                    flags.append(f)

            flags.append(Flag(
                severity=FlagSeverity.INFO,
                element_code="PENSION",
                code="STAT_PAY_PENSION_INFO_NEEDED",
                message=(
                    "We've detected statutory pay on your payslip. Your employer's "
                    "pension contributions during parental leave should be based on "
                    "your normal salary — not your statutory pay amount. We need a "
                    "little more information to check this fully. Please complete "
                    "the section below."
                ),
            ))
            # Trigger Stage 2 prompt
            flags.append(Flag(
                severity=FlagSeverity.INFO,
                element_code="STAT_PAY",
                code="PARENTAL_PAY_STAGE2_PROMPT",
                message="PARENTAL_PAY_DETECTED",
            ))

        else:
            # No stat pay — run full pension validation
            gross_for_tax_changed = sacrifice_amt > 0 or any(
                line.element_code == "C4" for line in payslip.pay_lines
            )
            gross_for_ni_changed = effective_has_sacrifice

            pension_breakdown, pension_flags = calculate_pension(
                gross_for_tax=gross_for_tax,
                gross_for_ni=gross_for_ni,
                ni_able_earnings=gross_for_ni,
                ee_contribution_shown=effective_ee_pension,
                er_contribution_shown=effective_er_pension,
                has_sacrifice_line=effective_has_sacrifice,
                sacrifice_amount=sacrifice_amt,
                gross_for_tax_changed=gross_for_tax_changed,
                gross_for_ni_changed=gross_for_ni_changed,
                software=payslip.software,
                provider=payslip.pension.provider or payslip.user_answers.pension_provider,
                frequency=frequency,
            )
            flags.extend(pension_flags)

            # B5 non-pension sacrifice alongside a SEPARATE pension — warn user
            if gross["has_b5_non_pension"] and has_sacrifice and not b5_is_pension_sacrifice:
                flags.append(Flag(
                    severity=FlagSeverity.WARNING,
                    element_code="PENSION",
                    code="B5_REDUCING_PENSION",
                    message=(
                        "Salary sacrifice is reducing your pensionable pay. Your employer "
                        "may not know this is the case so speak with HR to determine if "
                        "this is deliberate. The Pensions Regulator advise that it is up "
                        "to the employer if other salary sacrifice deductions reduce your "
                        "pensionable pay, there is no right or wrong here."
                    ),
                ))

            # SSP pension check (non-parental stat pay)
            has_ssp = any(l.element_code == "A18" for l in payslip.pay_lines)
            if has_ssp:
                pension_type_str = "SALARY_SACRIFICE" if effective_has_sacrifice else "NON_SAL_SAC"
                stat_flags, _, _, _ = validate_stat_pay_pension(
                    pay_lines=payslip.pay_lines,
                    ee_pension_shown=effective_ee_pension,
                    er_pension_shown=effective_er_pension,
                    sacrifice_amount=sacrifice_amt,
                    pension_type=pension_type_str,
                    payslip_frequency=frequency,
                )
                flags.extend(stat_flags)

    # --- STUDENT LOAN ---
    student_loan_deduction = 0.0
    student_loan_lines = [
        line for line in payslip.pay_lines
        if line.element_code in ("B1", "B2")
    ]
    if student_loan_lines:
        for sl_line in student_loan_lines:
            plan = "PGL" if sl_line.element_code == "B2" else None
            # Try to identify plan from description
            desc_lower = sl_line.description.lower()
            if "plan 1" in desc_lower or "plan1" in desc_lower:
                plan = "Plan1"
            elif "plan 2" in desc_lower or "plan2" in desc_lower:
                plan = "Plan2"
            elif "plan 4" in desc_lower or "plan4" in desc_lower:
                plan = "Plan4"
            elif "plan 5" in desc_lower or "plan5" in desc_lower:
                plan = "Plan5"
            elif "postgrad" in desc_lower or "pgl" in desc_lower:
                plan = "PGL"

            sl_flags = validate_student_loan(
                ni_able_earnings=gross_for_ni,
                deduction_shown=abs(sl_line.amount),
                plan=plan,
                tax_year=tax_year,
                frequency=frequency,
            )
            flags.extend(sl_flags)
            student_loan_deduction += abs(sl_line.amount)

    # --- NET PAY ---
    # Base: total gross (all positive payments including salary, stat pay etc.)
    # minus salary sacrifice/NPA (already in gross_for_tax reduction)
    # For RAS pension: the employee's net contribution (80%) also deducts from net pay
    # since gross_for_tax is unchanged for RAS.
    ras_pension_deduction = 0.0
    if pension_breakdown and pension_breakdown.pension_type == PensionType.RAS:
        ras_pension_deduction = pension_breakdown.ee_contribution_expected or 0.0

    net_pay_expected = round(
        gross_for_tax
        - tax_expected
        - ee_ni_expected
        - student_loan_deduction
        - ras_pension_deduction,
        2
    )
    net_pay_shown = payslip.summary.net_pay or 0.0
    net_pay_variance = round(abs(net_pay_expected - net_pay_shown), 2)

    return ValidationResult(
        gross_for_tax_calculated=gross_for_tax,
        earnings_for_ni_calculated=gross_for_ni,
        tax_expected=tax_expected,
        ee_ni_expected=ee_ni_expected,
        er_ni_expected=er_ni_expected,
        net_pay_expected=net_pay_expected,
        tax_variance=tax_variance,
        ee_ni_variance=ee_ni_variance,
        net_pay_variance=net_pay_variance,
        pension_breakdown=pension_breakdown,
        tax_breakdown=tax_breakdown,
        ni_breakdown=ni_breakdown,
        flags=flags,
        pay_frequency_confirmed=PayFrequency(frequency),
        tax_year_confirmed=tax_year,
    )
