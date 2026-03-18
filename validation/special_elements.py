"""
Wagestop — Special Pay Elements Handler
Tronc, BIK, Redundancy, PILON — each with specific tax/NI/pension treatment.
All flag wording is pre-approved — never auto-generated.
"""

from typing import List
from .models import Flag, FlagSeverity, PayLine


# ---------------------------------------------------------------------------
# TRONC (A12)
# ---------------------------------------------------------------------------

def handle_tronc(tronc_amount: float,
                 ni_was_deducted: bool) -> List[Flag]:
    """
    Tronc is always taxable.
    NICable or non-NICable depends on whether employer controls distribution.
    Payslip shows which treatment was applied — we flag to inform the user.
    """
    flags = []

    if not ni_was_deducted:
        flags.append(Flag(
            severity=FlagSeverity.INFO,
            element_code="TRONC",
            code="TRONC_NOT_NICABLE",
            message=(
                "Your Tronc pay is taxed as expected, but you don't pay National "
                "Insurance on this amount. Just so you know, a payment of this type "
                "means your employer doesn't directly have any input into how Tronc "
                "payments are distributed between staff. This is great news for you "
                "as it means you pay a bit less in national insurance!"
            ),
        ))
    else:
        flags.append(Flag(
            severity=FlagSeverity.INFO,
            element_code="TRONC",
            code="TRONC_NICABLE",
            message=(
                "Your Tronc pay is taxed and you pay National Insurance on this "
                "amount. This means your employer has influence on how Tronc payments "
                "are distributed between staff."
            ),
        ))

    return flags


def is_tronc_in_ni(tronc_amount: float,
                    gross_for_ni: float,
                    gross_for_tax: float) -> bool:
    """
    Determine if Tronc was included in NI calculation.
    If gross_for_ni < gross_for_tax and difference ≈ tronc_amount → not NICable.
    """
    difference = gross_for_tax - gross_for_ni
    return abs(difference - tronc_amount) > 1.00  # If difference ≠ tronc → NICable


# ---------------------------------------------------------------------------
# BENEFITS IN KIND — BIK (D1, D2, D3)
# ---------------------------------------------------------------------------

def handle_bik(bik_amount: float,
               bik_type: str) -> List[Flag]:
    """
    BIK is taxable but NOT included in net pay.
    It increases gross for tax only — no cash deduction from pay.
    """
    flags = []

    bik_names = {
        "D1": "Healthcare benefit",
        "D2": "Medical/dental benefit",
        "D3": "Company car/van benefit",
        "D100": "Benefit in kind",
    }
    name = bik_names.get(bik_type, "Benefit in kind")

    flags.append(Flag(
        severity=FlagSeverity.INFO,
        element_code=bik_type,
        code="BIK_EXPLAINED",
        message=(
            f"Your {name} of £{bik_amount:.2f} is a taxable benefit. "
            f"This increases your taxable pay and therefore your tax, but it is "
            f"not a cash deduction from your take-home pay — it's the value of a "
            f"benefit your employer provides."
        ),
    ))

    return flags


# ---------------------------------------------------------------------------
# REDUNDANCY (A15)
# ---------------------------------------------------------------------------

REDUNDANCY_EXEMPT_THRESHOLD = 30000.00


def handle_redundancy(redundancy_amount: float) -> tuple[float, float, List[Flag]]:
    """
    First £30,000 is tax-free.
    Amount above £30,000 is taxable.
    Not NICable regardless of amount.
    Returns (taxable_amount, non_taxable_amount, flags)
    """
    flags = []

    if redundancy_amount <= REDUNDANCY_EXEMPT_THRESHOLD:
        taxable = 0.0
        non_taxable = redundancy_amount
    else:
        taxable = round(redundancy_amount - REDUNDANCY_EXEMPT_THRESHOLD, 2)
        non_taxable = REDUNDANCY_EXEMPT_THRESHOLD
        flags.append(Flag(
            severity=FlagSeverity.INFO,
            element_code="REDUNDANCY",
            code="REDUNDANCY_OVER_THRESHOLD",
            message=(
                "As your redundancy pay exceeds £30,000, you are taxed on the "
                "excess in accordance with HMRC regulation."
            ),
            expected=REDUNDANCY_EXEMPT_THRESHOLD,
            actual=redundancy_amount,
        ))

    return taxable, non_taxable, flags


# ---------------------------------------------------------------------------
# PILON — Payment in Lieu of Notice (A14)
# ---------------------------------------------------------------------------

def handle_pilon(pilon_amount: float) -> tuple[float, List[Flag]]:
    """
    PILON is always fully taxable and NICable.
    It is not pensionable (non-earnings for pension).
    Returns (taxable_amount, flags)
    """
    flags = []

    flags.append(Flag(
        severity=FlagSeverity.INFO,
        element_code="PILON",
        code="PILON_EXPLAINED",
        message=(
            f"Your Payment in Lieu of Notice (PILON) of £{pilon_amount:.2f} is "
            f"fully subject to tax and National Insurance in the same way as "
            f"normal pay."
        ),
    ))

    return pilon_amount, flags


# ---------------------------------------------------------------------------
# ELEMENT SCANNER — detect special elements in pay lines
# ---------------------------------------------------------------------------

def scan_special_elements(pay_lines: List[PayLine],
                            gross_for_tax: float,
                            gross_for_ni: float) -> tuple[dict, List[Flag]]:
    """
    Scan all pay lines for special elements and return:
    - adjustments dict (any changes to gross figures)
    - flags list
    """
    flags = []
    adjustments = {
        "bik_total": 0.0,
        "redundancy_taxable": 0.0,
        "redundancy_non_taxable": 0.0,
        "tronc_total": 0.0,
        "pilon_total": 0.0,
    }

    for line in pay_lines:
        code = line.element_code
        amount = abs(line.amount)

        # --- TRONC ---
        if code == "A12":
            adjustments["tronc_total"] += amount
            ni_included = is_tronc_in_ni(amount, gross_for_ni, gross_for_tax)
            tronc_flags = handle_tronc(amount, ni_included)
            flags.extend(tronc_flags)

        # --- BIK ---
        elif code in ("D1", "D2", "D3", "D100"):
            adjustments["bik_total"] += amount
            bik_flags = handle_bik(amount, code)
            flags.extend(bik_flags)

        # --- REDUNDANCY ---
        elif code == "A15":
            taxable, non_taxable, red_flags = handle_redundancy(amount)
            adjustments["redundancy_taxable"] += taxable
            adjustments["redundancy_non_taxable"] += non_taxable
            flags.extend(red_flags)

        # --- PILON ---
        elif code == "A14":
            adjustments["pilon_total"] += amount
            _, pilon_flags = handle_pilon(amount)
            flags.extend(pilon_flags)

    return adjustments, flags
