"""
Wagestop — Pay Elements Classifier
Maps payslip line descriptions to element codes (A1, B5 etc.)
Used after OCR extraction to classify each pay line.
"""

import re
from typing import Optional


# ---------------------------------------------------------------------------
# ELEMENT KEYWORD MAP
# Ordered from most specific to least specific within each category
# ---------------------------------------------------------------------------

ELEMENT_KEYWORDS = {
    # --- PAYMENTS ---
    "A1":  ["salary", "basic", "base", "wage", "wages", "hours", "hrs",
             "gross", "monthly pay", "regular", "weekly pay"],
    "A2":  ["overtime", "additional hours", "extra hours"],
    "A3":  ["holiday pay", "holiday", "hols", "annual leave"],
    "A4":  ["back pay", "arrears", "adjustment", "backpay"],
    "A5":  ["commission", "comm"],
    "A6":  ["bonus"],
    "A7":  ["on call", "on-call", "standby"],
    "A8":  ["incentive", "increased rate", "additional rate"],
    "A9":  ["car allowance", "car allow", "vehicle allowance"],
    "A10": ["mobile allowance", "mob allow", "phone allowance", "mobile allow"],
    "A11": ["work from home", "wfh", "home working allowance"],
    "A12": ["tronc", "gratuities", "gratuity", "tips"],
    "A13": ["expense", "reimbursement", "refund", "expenses"],
    "A14": ["pilon", "payment in lieu", "pay in lieu"],
    "A15": ["redundancy", "ex gratia", "severance"],
    "A16": ["smp", "statutory maternity", "maternity pay"],
    "A17": ["spp", "statutory paternity", "paternity pay"],
    "A18": ["ssp", "statutory sick", "sick pay"],
    "A19": ["enhanced pay", "enhanced maternity", "top up", "enhancement"],
    # Parental pay covers SMP and SPP
    "A16_OR_A17": ["parental pay", "statutory parental", "parental leave pay"],
    # SAP and ShPP treated same as SMP/SPP
    "A16": ["sap", "statutory adoption", "adoption pay",
            "shpp", "shared parental", "spbp", "sncp"],

    # --- DEDUCTIONS ---
    "B1":  ["student loan", "st loan", "stl", "plan 1", "plan 2",
             "plan 3", "plan 4", "plan 5"],
    "B2":  ["post graduate loan", "postgraduate loan", "pg loan", "pgl"],
    "B3":  ["unpaid leave", "unpaid holiday", "unpaid absence"],
    "B4":  ["unpaid sick", "absence deduction", "sick deduction"],
    "B5":  ["salary sacrifice", "cycle", "c2w", "cycle to work",
             "salsac", "sal sac", "cycle scheme"],
    "B6":  ["loan repayment", "loan", "staff loan"],
    "B7":  ["net deduction", "net adjustment", "deduction"],
    "B8":  ["personal expense", "personal deduction"],

    # --- CALCULATED DEDUCTIONS ---
    "C1":  ["paye", "income tax", "tax", "taxes"],
    "C2":  ["national insurance", "ni", "nic", "employee ni",
             "ee ni", "eee ni", "employee nic"],
    "C3":  ["pension", "ae pension", "employee pension", "ee pension",
             "eee pen", "nest", "smart", "now pensions", "the people",
             "peoples pension", "cushon", "aegon", "true potential",
             "royal london", "aviva", "scottish widows", "ras"],
    "C4":  ["npa pension", "net pay pension"],
    "C5":  ["sacrifice pension", "ss pension", "pension sacrifice"],
    "C6":  ["avc", "additional voluntary", "voluntary pension"],

    # --- BENEFITS IN KIND ---
    "D1":  ["healthcare", "health care", "bupa", "health benefit"],
    "D2":  ["medical", "dental", "medical benefit"],
    "D3":  ["car benefit", "company car", "vehicle benefit",
             "van benefit", "ev benefit", "fuel benefit", "bik"],

    # --- EMPLOYER COSTS ---
    "E1":  ["employer ni", "er ni", "employer nic", "er nic",
             "employers ni", "employers nic"],
    "E3":  ["employer pension", "er pension", "er pen",
             "employers pension", "employer contribution"],
}

# Build reverse lookup: keyword -> element_code
_KEYWORD_TO_CODE = {}
for code, keywords in ELEMENT_KEYWORDS.items():
    for kw in keywords:
        _KEYWORD_TO_CODE[kw.lower()] = code


# ---------------------------------------------------------------------------
# ELEMENT CATEGORIES (for grouping on the review screen)
# ---------------------------------------------------------------------------

ELEMENT_CATEGORIES = {
    "Payments": [
        "A1","A2","A3","A4","A5","A6","A7","A8","A9","A10",
        "A11","A12","A13","A14","A15","A16","A17","A18","A19",
        "A16_OR_A17",
    ],
    "Deductions": ["B1","B2","B3","B4","B5","B6","B7","B8"],
    "Pension":    ["C3","C4","C5","C6"],
    "Tax & NI":   ["C1","C2"],
    "Benefits":   ["D1","D2","D3"],
    "Employer Costs": ["E1","E3"],
}


def get_category(element_code: str) -> str:
    """Return the display category for an element code"""
    for category, codes in ELEMENT_CATEGORIES.items():
        if element_code in codes:
            return category
    return "Other"


# ---------------------------------------------------------------------------
# CLASSIFIER
# ---------------------------------------------------------------------------

def classify_element(description: str) -> Optional[str]:
    """
    Classify a payslip line description to an element code.
    Uses keyword matching — longest match wins.
    Returns element code string or None if unclassified.
    """
    desc_lower = description.lower().strip()

    # Try longest keyword match first (most specific)
    best_match = None
    best_length = 0

    for keyword, code in _KEYWORD_TO_CODE.items():
        if keyword in desc_lower and len(keyword) > best_length:
            best_match = code
            best_length = len(keyword)

    return best_match


def classify_pay_lines(raw_lines: list) -> list:
    """
    Classify a list of raw OCR-extracted lines.
    Each raw line: {"description": str, "amount": float, ...}
    Returns list with element_code added.
    """
    classified = []
    for line in raw_lines:
        desc = line.get("description", "")
        code = classify_element(desc)
        classified.append({
            **line,
            "element_code": code or "A100",    # A100 = unclassified
            "category": get_category(code) if code else "Other",
            "is_unclassified": code is None,
        })
    return classified


# ---------------------------------------------------------------------------
# ELEMENT METADATA (for UI display)
# ---------------------------------------------------------------------------

ELEMENT_DISPLAY_NAMES = {
    "A1": "Salary / Basic Pay",
    "A2": "Overtime",
    "A3": "Holiday Pay",
    "A4": "Back Pay / Arrears",
    "A5": "Commission",
    "A6": "Bonus",
    "A7": "On Call",
    "A8": "Incentive",
    "A9": "Car Allowance",
    "A10": "Mobile Allowance",
    "A11": "Work from Home Allowance",
    "A12": "Tronc / Gratuities",
    "A13": "Expenses",
    "A14": "PILON",
    "A15": "Redundancy",
    "A16": "Statutory Maternity Pay (SMP)",
    "A17": "Statutory Paternity Pay (SPP)",
    "A18": "Statutory Sick Pay (SSP)",
    "A19": "Enhanced Pay",
    "A16_OR_A17": "Parental Pay",
    "B1": "Student Loan",
    "B2": "Postgraduate Loan",
    "B3": "Unpaid Leave",
    "B4": "Unpaid Sick",
    "B5": "Salary Sacrifice",
    "B6": "Loan Repayment",
    "B7": "Net Deduction",
    "B8": "Personal Expense",
    "C1": "Income Tax",
    "C2": "National Insurance",
    "C3": "Pension (RAS)",
    "C4": "Pension (NPA)",
    "C5": "Pension (Salary Sacrifice)",
    "C6": "AVC",
    "D1": "Healthcare Benefit",
    "D2": "Medical / Dental Benefit",
    "D3": "Car / Van Benefit",
    "E1": "Employer NI",
    "E3": "Employer Pension",
    "A100": "Other (unclassified)",
}


def get_display_name(element_code: str) -> str:
    return ELEMENT_DISPLAY_NAMES.get(element_code, element_code)
