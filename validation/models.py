"""
Wagestop — Input and Output Data Models
Defines all data structures passed between the UI, OCR engine, and validation engine.
"""

from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


# ---------------------------------------------------------------------------
# ENUMS
# ---------------------------------------------------------------------------

class PayFrequency(Enum):
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    UNKNOWN = "unknown"

class PensionType(Enum):
    RAS = "Relief at Source (RAS)"
    NPA = "Net Pay Arrangement (NPA)"
    SALARY_SACRIFICE = "Salary Sacrifice"
    UNKNOWN = "unknown"

class PensionBasis(Enum):
    QUALIFYING_EARNINGS = "Qualifying Earnings"
    ALL_PAY = "All Pay"
    BASIC_PAY = "Basic Pay"
    EARNINGS_85 = "85% of Earnings"
    UNKNOWN = "unknown"

class TaxYear(Enum):
    Y2024_25 = "2024/25"
    Y2025_26 = "2025/26"
    Y2026_27 = "2026/27"

class FlagSeverity(Enum):
    ERROR = "error"         # Definite calculation error
    WARNING = "warning"     # Potential issue requiring attention
    INFO = "info"           # Informational — not an error


# ---------------------------------------------------------------------------
# PRE-SCAN USER ANSWERS
# ---------------------------------------------------------------------------

@dataclass
class EmployerMatchingRule:
    """Q7 — how employer matches employee pension contribution"""
    match_type: str                     # "up_to_max", "pct_higher", "pct_lower", "unsure"
    match_pct: Optional[float] = None   # The percentage figure entered

@dataclass
class UserAnswers:
    """All answers collected from pre-scan questions Q1–Q9 and MW1–MW14"""

    # Q1 — Pay frequency
    pay_frequency: PayFrequency = PayFrequency.UNKNOWN

    # Q2 — Pension enrolled
    pension_enrolled: Optional[bool] = None     # None = unsure

    # Q3 — Pension provider
    pension_provider: Optional[str] = None

    # Q4 — Knows minimum contribution
    knows_min_contribution: Optional[bool] = None

    # Q5 — Employee contribution (a/b/c)
    ee_min_contribution_pct: Optional[float] = None
    ee_min_contribution_gbp: Optional[float] = None
    ee_additional_pct: Optional[float] = None
    ee_additional_gbp: Optional[float] = None
    ee_total_contribution_pct: Optional[float] = None
    ee_total_contribution_gbp: Optional[float] = None

    # Q6 — Employer contribution
    er_min_contribution_pct: Optional[float] = None
    er_matching: bool = False

    # Q7 — Employer matching detail
    er_matching_rule: Optional[EmployerMatchingRule] = None

    # Q8 — Minimum wage check
    min_wage_check: bool = False

    # Q9 — Date of birth
    date_of_birth: Optional[str] = None     # ISO format YYYY-MM-DD

    # MW questions — minimum wage
    contractual_weekly_hours: Optional[float] = None
    hours_worked_this_period: Optional[float] = None
    is_apprentice: Optional[bool] = None
    apprentice_first_year: Optional[bool] = None
    early_start_required: Optional[bool] = None
    unpaid_overtime: Optional[bool] = None
    travels_between_clients: Optional[bool] = None
    travel_reimbursed: Optional[bool] = None
    paid_for_travel_time: Optional[bool] = None
    unpaid_travel_hours: Optional[float] = None
    shift_rounding: Optional[bool] = None
    unpaid_training: Optional[bool] = None
    employer_records_hours: Optional[bool] = None
    supplies_own_uniform: Optional[bool] = None


# ---------------------------------------------------------------------------
# PAYSLIP INPUT — PAY LINES
# ---------------------------------------------------------------------------

@dataclass
class PayLine:
    """A single payment or deduction line extracted from the payslip"""
    element_code: str           # e.g. "A1", "B5", "C3"
    description: str            # As shown on payslip e.g. "Basic Salary"
    amount: float               # Positive for payments, negative for deductions
    units: Optional[float] = None
    rate: Optional[float] = None
    is_user_amended: bool = False   # True if user manually edited this line


@dataclass
class PensionInput:
    """Pension figures extracted from payslip"""
    provider: Optional[str] = None
    ee_contribution_shown: Optional[float] = None
    er_contribution_shown: Optional[float] = None
    ytd_ee_pension: Optional[float] = None
    ytd_er_pension: Optional[float] = None


@dataclass
class PayslipSummaryFigures:
    """
    Summary figures as shown on payslip.
    Used for cross-checking ONLY — never used in calculations.
    All calculations are built independently from pay lines.
    """
    total_gross_pay: Optional[float] = None
    gross_for_tax: Optional[float] = None
    earnings_for_ni: Optional[float] = None
    tax_paid: Optional[float] = None
    ni_paid: Optional[float] = None
    net_pay: Optional[float] = None


@dataclass
class YTDFigures:
    """Year to date figures from payslip"""
    ytd_gross: Optional[float] = None
    ytd_gross_for_tax: Optional[float] = None
    ytd_tax_paid: Optional[float] = None
    ytd_ni_paid: Optional[float] = None
    ytd_earnings_for_ni: Optional[float] = None


@dataclass
class PayslipInput:
    """
    Complete payslip input — everything the validation engine needs.
    Built from OCR extraction + user confirmation.
    """
    # Metadata
    payment_date: str               # ISO format YYYY-MM-DD
    tax_code: str                   # e.g. "1257L", "K407", "BR"
    ni_category: str = "A"          # Default Cat A if not shown
    pay_frequency: PayFrequency = PayFrequency.MONTHLY
    tax_year: TaxYear = TaxYear.Y2025_26
    tax_period: Optional[int] = None    # Month 1-12 or Week 1-53
    software: Optional[str] = None      # e.g. "Sage 50 Desktop", "BrightPay"

    # Pay lines (extracted and user-confirmed)
    pay_lines: List[PayLine] = field(default_factory=list)

    # Pension
    pension: PensionInput = field(default_factory=PensionInput)

    # Summary figures (cross-check only)
    summary: PayslipSummaryFigures = field(default_factory=PayslipSummaryFigures)

    # YTD
    ytd: YTDFigures = field(default_factory=YTDFigures)

    # User pre-scan answers
    user_answers: UserAnswers = field(default_factory=UserAnswers)


# ---------------------------------------------------------------------------
# VALIDATION OUTPUT
# ---------------------------------------------------------------------------

@dataclass
class Flag:
    """A single validation flag — error, warning or info"""
    severity: FlagSeverity
    element_code: str           # Which element this flag relates to e.g. "TAX", "PENSION_ER"
    code: str                   # Internal flag code e.g. "TAX_DISCREPANCY"
    message: str                # User-facing message (pre-approved wording only)
    expected: Optional[float] = None
    actual: Optional[float] = None
    variance: Optional[float] = None


@dataclass
class TaxBreakdown:
    """Drill-down tax calculation detail"""
    tax_code: str
    is_k_code: bool
    is_emergency: bool
    is_scottish: bool
    free_pay_annual: float
    free_pay_period: float
    k_addition: Optional[float]
    ytd_gross_for_tax: float
    ytd_taxable: float
    ytd_taxable_rounded: float
    bands_applied: List[dict]       # [{band, from, to, rate, tax}]
    ytd_tax_calculated: float
    prior_period_tax: float
    tax_this_period: float
    cap_applied: bool
    cap_limit: Optional[float]


@dataclass
class NIBreakdown:
    """Drill-down NI calculation detail"""
    ni_category: str
    gross_for_ni: float
    bands_applied: List[dict]       # [{band, from, to, rate, ni}]
    ee_ni_calculated: float
    er_ni_calculated: float
    sage_uel_display: bool          # True if Sage capped display at UEL


@dataclass
class PensionBreakdown:
    """Drill-down pension calculation detail"""
    pension_type: PensionType
    pension_basis: PensionBasis
    provider: Optional[str]
    pensionable_pay: float
    ee_contribution_expected: float
    er_contribution_expected: float
    er_true_contribution: float     # After removing sacrifice from combined figure
    combined_er_shown: Optional[float]
    tpr_total_min_pct: float
    tpr_er_min_pct: float
    tpr_ee_min_pct: float
    tpr_total_met: bool
    tpr_er_met: bool
    tpr_ee_met: bool


@dataclass
class ValidationResult:
    """
    Complete validation output returned by the engine.
    Consumed by the website to display results and drill-downs.
    """
    # Calculated figures
    gross_for_tax_calculated: float
    earnings_for_ni_calculated: float
    tax_expected: float
    ee_ni_expected: float
    er_ni_expected: float
    net_pay_expected: float

    # Variances
    tax_variance: float
    ee_ni_variance: float
    net_pay_variance: float

    # Pension
    pension_breakdown: Optional[PensionBreakdown]

    # Drill-down detail
    tax_breakdown: TaxBreakdown
    ni_breakdown: NIBreakdown

    # All flags — grouped by element code
    flags: List[Flag] = field(default_factory=list)

    # Pay frequency confirmed from payslip
    pay_frequency_confirmed: PayFrequency = PayFrequency.MONTHLY

    # Tax year confirmed
    tax_year_confirmed: TaxYear = TaxYear.Y2025_26

    def flags_for(self, element_code: str) -> List[Flag]:
        """Return all flags for a specific element"""
        return [f for f in self.flags if f.element_code == element_code]

    def has_errors(self) -> bool:
        return any(f.severity == FlagSeverity.ERROR for f in self.flags)

    def has_warnings(self) -> bool:
        return any(f.severity == FlagSeverity.WARNING for f in self.flags)
