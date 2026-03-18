"""
Wagestop — Statutory Pay Validation Engine
Handles SMP, SPP, SAP, ShPP, SSP pension interactions.
Two-stage validation: Stage 1 from payslip, Stage 2 from pre-leave data.
All flag wording is pre-approved — never auto-generated.
"""

import math
from typing import Optional
from .models import Flag, FlagSeverity, TaxYear, PayFrequency


# ---------------------------------------------------------------------------
# STATUTORY PAY WEEKLY RATES 2025/26
# ---------------------------------------------------------------------------

STATUTORY_RATES = {
    TaxYear.Y2025_26: {
        "SMP_STANDARD": 187.18,     # SMP weeks 7+ (or 90% AWE if lower)
        "SPP": 187.18,
        "SAP_STANDARD": 187.18,
        "ShPP": 187.18,
        "SSP": 118.75,
        "SSP_DAILY": {
            7: 16.97, 6: 19.80, 5: 23.75,
            4: 29.69, 3: 39.59, 2: 59.38, 1: 118.75
        },
    },
    TaxYear.Y2024_25: {
        "SMP_STANDARD": 184.03,
        "SPP": 184.03,
        "SAP_STANDARD": 184.03,
        "ShPP": 184.03,
        "SSP": 116.75,
        "SSP_DAILY": {
            7: 16.68, 6: 19.46, 5: 23.35,
            4: 29.19, 3: 38.92, 2: 58.38, 1: 116.75
        },
    },
    TaxYear.Y2026_27: {
        "SMP_STANDARD": 187.18,     # Update when confirmed
        "SPP": 187.18,
        "SAP_STANDARD": 187.18,
        "ShPP": 187.18,
        "SSP": 118.75,
        "SSP_DAILY": {
            7: 16.97, 6: 19.80, 5: 23.75,
            4: 29.69, 3: 39.59, 2: 59.38, 1: 118.75
        },
    },
}

COMMON_PENSION_RATES = [
    0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12, 0.15, 0.20
]
STAT_PAY_TOLERANCE = 0.10

LEL = {"monthly": 520.00, "weekly": 120.00}

# Stat pay element codes — SMP, SPP, SAP, ShPP (not SSP)
PARENTAL_STAT_PAY_CODES = {"A16", "A17", "A16_OR_A17"}
SSP_CODE = "A18"


# ---------------------------------------------------------------------------
# STAGE 1 — CHECK IF Er IS BASED SOLELY ON PAYSLIP AMOUNTS
# ---------------------------------------------------------------------------

def er_appears_based_on_payslip_only(er_pension: float,
                                      stat_pay: float,
                                      other_pensionable: float = 0.0,
                                      pension_type: str = "NON_SAL_SAC") -> bool:
    """
    Returns True if Er pension matches (stat_pay + other_pensionable) x
    any common rate — suggesting Er is based on payslip amounts only,
    not pre-leave salary.
    """
    if pension_type == "SALARY_SACRIFICE":
        test_basis = stat_pay + other_pensionable
    else:
        test_basis = stat_pay  # Non-sal-sac: test against stat pay alone

    for rate in COMMON_PENSION_RATES:
        if abs(er_pension - round(test_basis * rate, 2)) <= STAT_PAY_TOLERANCE:
            return True
    return False


def stage1_stat_pay_pension_check(er_pension: float,
                                   stat_pay: float,
                                   other_pensionable: float,
                                   pension_type: str) -> Optional[Flag]:
    """
    Stage 1: Check Er pension on parental leave payslip.
    Returns flag if Er appears to be based on payslip amounts only.
    """
    if er_appears_based_on_payslip_only(
        er_pension, stat_pay, other_pensionable, pension_type
    ):
        if pension_type == "SALARY_SACRIFICE":
            return Flag(
                severity=FlagSeverity.WARNING,
                element_code="PENSION_ER",
                code="ER_PENSION_PAYSLIP_ONLY_SAL_SAC",
                message=(
                    "You are owed money!! It's your employer's responsibility to pay "
                    "both yours and their pension contributions for the whole of your "
                    "parental leave. This amount should be at the same level as it was "
                    "before you started your statutory leave (so based on your normal "
                    "salary as if you were still at work). Your payslip shows this at a "
                    "lower level and so your employer will owe you money which they need "
                    "to pay into your pension pot. Any underpayment should be calculated "
                    "from the start of your statutory leave. See our email templates if "
                    "you would like us to automate an email template for you to send to "
                    "your employer."
                ),
            )
        else:
            return Flag(
                severity=FlagSeverity.WARNING,
                element_code="PENSION_ER",
                code="ER_PENSION_STAT_PAY_ONLY",
                message=(
                    "Your employer's pension contribution should be at the same level "
                    "as it was before you started your statutory leave, and should be "
                    "paid at that rate for the whole of your leave period. Your payslip "
                    "shows this at a lower level and so your employer will owe you money "
                    "which they need to pay into your pension pot. Any underpayment "
                    "should be calculated from the start of your statutory leave. See "
                    "our email templates if you would like us to automate an email "
                    "template for you to send to your employer so you can reclaim "
                    "this money."
                ),
            )
    return None


# ---------------------------------------------------------------------------
# STAGE 2 — CALCULATE EXPECTED Er FROM PRE-LEAVE DATA
# ---------------------------------------------------------------------------

def normalise_to_payslip_frequency(salary: float,
                                    input_frequency: str,
                                    payslip_frequency: str) -> float:
    """Convert pre-leave salary to match current payslip frequency."""
    if input_frequency == "monthly":
        annual = salary * 12
    elif input_frequency == "weekly":
        annual = salary * 52
    else:
        annual = salary

    if payslip_frequency == "monthly":
        return annual / 12
    else:
        return annual / 52


def derive_pension_basis_from_pre_leave(normalised_salary: float,
                                         pre_leave_er_pension: float,
                                         payslip_frequency: str) -> tuple:
    """
    Determine QE or All Pay from pre-leave payslip data.
    Returns (basis, er_rate)
    """
    lel = LEL[payslip_frequency]
    qe_base = normalised_salary - lel

    if qe_base > 0:
        for rate in COMMON_PENSION_RATES:
            if abs(pre_leave_er_pension - round(qe_base * rate, 2)) <= STAT_PAY_TOLERANCE:
                return "QE", rate

    for rate in COMMON_PENSION_RATES:
        if abs(pre_leave_er_pension - round(normalised_salary * rate, 2)) <= STAT_PAY_TOLERANCE:
            return "ALL_PAY", rate

    return "UNKNOWN", None


def stage2_calculate_expected_er(pre_leave_salary: float,
                                  pre_leave_salary_frequency: str,
                                  pre_leave_ee_pension: float,
                                  pre_leave_er_pension: float,
                                  other_pensionable_on_payslip: float,
                                  is_salary_sacrifice: bool,
                                  payslip_frequency: str) -> tuple:
    """
    Stage 2: Calculate expected Er using pre-leave data.
    Returns (expected_er, basis, flag_or_none)
    """
    normalised = normalise_to_payslip_frequency(
        pre_leave_salary, pre_leave_salary_frequency, payslip_frequency
    )
    basis, er_rate = derive_pension_basis_from_pre_leave(
        normalised, pre_leave_er_pension, payslip_frequency
    )
    lel = LEL[payslip_frequency]
    pensionable_base = (normalised - lel) if basis == "QE" else normalised

    if is_salary_sacrifice:
        ee_rate = pre_leave_ee_pension / pensionable_base if pensionable_base > 0 else 0
        combined_rate = ee_rate + (er_rate or 0)
        ee_sacrifice_on_other = round(other_pensionable_on_payslip * ee_rate, 2)
        expected_er = round((pensionable_base * combined_rate) - ee_sacrifice_on_other, 2)
    else:
        expected_er = round(pensionable_base * (er_rate or 0), 2)

    return expected_er, basis, None


def stage2_output_message(expected_er: float,
                           payslip_frequency: str) -> str:
    """
    Stage 2 output message — only shown if Stage 1 flag was raised
    AND Stage 2 confirms underpayment.
    """
    freq_label = "month" if payslip_frequency == "monthly" else "week"
    return (
        f"We estimate your employer contributions should have been "
        f"£{expected_er:.2f} a {freq_label} from the start of your leave. "
        f"You'll need to speak with your employer to ensure they pay any back "
        f"pay directly into your pension pot. You can use one of our email "
        f"templates which will automate all of the figures for you before you "
        f"send it to your employer."
    )


# ---------------------------------------------------------------------------
# SSP PENSION CHECK
# ---------------------------------------------------------------------------

def check_ssp_pension(ee_pension_shown: float,
                       ssp_amount: float,
                       other_pensionable: float,
                       pension_type: str) -> Optional[Flag]:
    """
    SSP is pensionable for Er under all types.
    For salary sacrifice: Ee cannot sacrifice SSP — Ee pension on SSP = 0.
    Check if Ee pension appears to include SSP amount.
    """
    if pension_type != "SALARY_SACRIFICE":
        return None  # SSP pensionable as normal for RAS/NPA

    # For salary sacrifice: Ee pension should be based on other_pensionable only
    # If Ee pension > what other_pensionable alone would produce → SSP included
    if other_pensionable > 0:
        for rate in COMMON_PENSION_RATES:
            expected_on_other = round(other_pensionable * rate, 2)
            if abs(ee_pension_shown - expected_on_other) <= STAT_PAY_TOLERANCE:
                return None  # Ee correctly based on other pensionable only

    # Ee pension appears to include SSP
    if ee_pension_shown > 0 and other_pensionable == 0:
        return Flag(
            severity=FlagSeverity.WARNING,
            element_code="PENSION_EE",
            code="SSP_INCLUDED_IN_EE_PENSION",
            message=(
                "Your Statutory Sick Pay cannot be included in your salary sacrifice "
                "pension calculation. Your employee pension contribution should be "
                "based only on your other pensionable pay, not your SSP."
            ),
        )
    return None


# ---------------------------------------------------------------------------
# MAIN STATUTORY PAY VALIDATOR
# ---------------------------------------------------------------------------

def validate_stat_pay_pension(pay_lines: list,
                               ee_pension_shown: float,
                               er_pension_shown: float,
                               sacrifice_amount: float,
                               pension_type: str,
                               payslip_frequency: str) -> list:
    """
    Main statutory pay pension validation.
    Returns list of Stage 1 flags.
    Stage 2 requires additional user input (handled in app.py).
    """
    flags = []

    # Identify stat pay amounts
    stat_pay_amount = 0.0
    other_pensionable = 0.0
    has_ssp = False
    has_parental = False

    for line in pay_lines:
        if line.element_code in PARENTAL_STAT_PAY_CODES:
            stat_pay_amount += line.amount
            has_parental = True
        elif line.element_code == SSP_CODE:
            stat_pay_amount += line.amount
            has_ssp = True
        elif line.element_code not in ("C1", "C2", "C3", "C4", "C5",
                                        "D1", "D2", "D3", "E1", "E3",
                                        "B1", "B2", "B5"):
            if line.amount > 0:
                other_pensionable += line.amount

    # SSP pension check
    if has_ssp:
        ssp_flag = check_ssp_pension(
            ee_pension_shown, stat_pay_amount, other_pensionable, pension_type
        )
        if ssp_flag:
            flags.append(ssp_flag)

    # Parental pay pension check (Stage 1)
    if has_parental and er_pension_shown > 0:
        stage1_flag = stage1_stat_pay_pension_check(
            er_pension_shown, stat_pay_amount, other_pensionable, pension_type
        )
        if stage1_flag:
            flags.append(stage1_flag)

    return flags, has_parental, stat_pay_amount, other_pensionable
