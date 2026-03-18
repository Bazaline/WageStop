"""
Wagestop — Flask Application
Main web application entry point.
"""

import os
import json
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify
)
from werkzeug.utils import secure_filename
from validation import (
    extract_payslip_data, build_payslip_input_from_extraction,
    validate_payslip, ELEMENT_CATEGORIES, get_display_name
)
from validation.models import (
    PayslipInput, PayLine, PensionInput, PayslipSummaryFigures,
    YTDFigures, UserAnswers, PayFrequency, TaxYear
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "wagestop-dev-key")

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "gif", "webp", "bmp", "tiff"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max


def allowed_file(filename):
    return "." in filename and \
           filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# HOME
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    return render_template("home.html")


# ---------------------------------------------------------------------------
# PRE-SCAN QUESTIONS
# ---------------------------------------------------------------------------

@app.route("/questions", methods=["GET", "POST"])
def questions():
    if request.method == "POST":
        # Save answers to session
        answers = {
            "pay_frequency":        request.form.get("pay_frequency", "unsure"),
            "pension_enrolled":     request.form.get("pension_enrolled"),
            "pension_provider":     request.form.get("pension_provider"),
            "knows_min_contribution": request.form.get("knows_min_contribution"),
            "ee_min_pct":           request.form.get("ee_min_pct"),
            "ee_min_gbp":           request.form.get("ee_min_gbp"),
            "ee_additional_pct":    request.form.get("ee_additional_pct"),
            "ee_additional_gbp":    request.form.get("ee_additional_gbp"),
            "ee_total_pct":         request.form.get("ee_total_pct"),
            "ee_total_gbp":         request.form.get("ee_total_gbp"),
            "er_min_pct":           request.form.get("er_min_pct"),
            "er_matching":          request.form.get("er_matching") == "yes",
            "er_match_type":        request.form.get("er_match_type"),
            "er_match_pct":         request.form.get("er_match_pct"),
            "min_wage_check":       request.form.get("min_wage_check") == "yes",
            "date_of_birth":        request.form.get("date_of_birth"),
            # MW questions
            "contractual_hours":    request.form.get("contractual_hours"),
            "hours_worked":         request.form.get("hours_worked"),
            "is_apprentice":        request.form.get("is_apprentice"),
            "apprentice_first_year": request.form.get("apprentice_first_year"),
            "early_start":          request.form.get("early_start"),
            "unpaid_overtime":      request.form.get("unpaid_overtime"),
            "travels_clients":      request.form.get("travels_clients"),
            "travel_reimbursed":    request.form.get("travel_reimbursed"),
            "paid_travel_time":     request.form.get("paid_travel_time"),
            "unpaid_travel_hours":  request.form.get("unpaid_travel_hours"),
            "shift_rounding":       request.form.get("shift_rounding"),
            "unpaid_training":      request.form.get("unpaid_training"),
            "employer_records_hours": request.form.get("employer_records_hours"),
            "own_uniform":          request.form.get("own_uniform"),
        }
        session["user_answers"] = answers
        return redirect(url_for("questions_summary"))

    return render_template("questions.html")


@app.route("/questions/summary")
def questions_summary():
    answers = session.get("user_answers", {})
    return render_template("questions_summary.html", answers=answers)


# ---------------------------------------------------------------------------
# PAYSLIP UPLOAD
# ---------------------------------------------------------------------------

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        if "payslip" not in request.files:
            return render_template("upload.html", error="Please select a file to upload.")

        file = request.files["payslip"]
        if file.filename == "":
            return render_template("upload.html", error="Please select a file to upload.")

        if not allowed_file(file.filename):
            return render_template("upload.html",
                                   error="Please upload a PDF, JPG, PNG or other image file.")

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        # Extract payslip data
        try:
            extracted = extract_payslip_data(filepath)
            structured = build_payslip_input_from_extraction(extracted)
            session["payslip_data"] = structured
            session["payslip_filepath"] = filepath
        except Exception as e:
            return render_template("upload.html",
                                   error=f"We couldn't read your payslip. Please try again. ({str(e)})")

        return redirect(url_for("review"))

    return render_template("upload.html")


# ---------------------------------------------------------------------------
# REVIEW SCREEN (editable breakdown)
# ---------------------------------------------------------------------------

@app.route("/review", methods=["GET", "POST"])
def review():
    if "payslip_data" not in session:
        return redirect(url_for("upload"))

    if request.method == "POST":
        # User has confirmed or amended the data
        # Rebuild pay lines from the submitted form
        confirmed_lines = []
        line_count = int(request.form.get("line_count", 0))

        for i in range(line_count):
            desc    = request.form.get(f"line_{i}_description", "")
            code    = request.form.get(f"line_{i}_element_code", "A100")
            amount  = request.form.get(f"line_{i}_amount", "0")
            amended = request.form.get(f"line_{i}_amended") == "1"

            try:
                amount_float = float(amount.replace(",", ""))
            except ValueError:
                amount_float = 0.0

            if desc.strip():
                confirmed_lines.append({
                    "description": desc,
                    "element_code": code,
                    "amount": amount_float,
                    "is_user_amended": amended,
                })

        # Update session with confirmed data
        payslip_data = session["payslip_data"]
        payslip_data["confirmed_lines"] = confirmed_lines

        # Update metadata from form
        payslip_data["metadata"]["tax_code"] = request.form.get(
            "tax_code", payslip_data["metadata"].get("tax_code", "1257L")
        )
        payslip_data["metadata"]["ni_category"] = request.form.get(
            "ni_category", payslip_data["metadata"].get("ni_category", "A")
        )
        payslip_data["metadata"]["payment_date"] = request.form.get(
            "payment_date", payslip_data["metadata"].get("payment_date", "")
        )

        # Pension figures
        payslip_data["pension"]["ee_contribution"] = request.form.get("ee_pension")
        payslip_data["pension"]["er_contribution"] = request.form.get("er_pension")

        # Summary figures
        payslip_data["summary"]["net_pay"] = request.form.get("net_pay")
        payslip_data["summary"]["tax_paid"] = request.form.get("tax_paid")
        payslip_data["summary"]["ni_paid"]  = request.form.get("ni_paid")

        session["payslip_data"] = payslip_data
        return redirect(url_for("analyse"))

    payslip_data = session["payslip_data"]
    return render_template(
        "review.html",
        payslip_data=payslip_data,
        element_categories=ELEMENT_CATEGORIES,
        get_display_name=get_display_name,
    )


# ---------------------------------------------------------------------------
# ANALYSIS
# ---------------------------------------------------------------------------

@app.route("/analyse")
def analyse():
    if "payslip_data" not in session:
        return redirect(url_for("upload"))

    payslip_data = session["payslip_data"]
    user_answers_raw = session.get("user_answers", {})

    # Build PayslipInput from confirmed data
    lines = payslip_data.get("confirmed_lines",
                             payslip_data.get("all_lines", []))
    pay_lines = [
        PayLine(
            element_code=line["element_code"],
            description=line["description"],
            amount=float(line["amount"]),
            is_user_amended=line.get("is_user_amended", False),
        )
        for line in lines
    ]

    meta = payslip_data.get("metadata", {})
    pension_raw = payslip_data.get("pension", {})
    summary_raw = payslip_data.get("summary", {})
    ytd_raw = payslip_data.get("ytd", {})

    def to_float(val):
        try:
            return float(val) if val else None
        except (TypeError, ValueError):
            return None

    payslip = PayslipInput(
        payment_date=meta.get("payment_date", ""),
        tax_code=meta.get("tax_code", "1257L"),
        ni_category=meta.get("ni_category", "A"),
        pay_frequency=PayFrequency(meta.get("pay_frequency", "monthly")),
        tax_period=meta.get("tax_period"),
        software=meta.get("software"),
        pay_lines=pay_lines,
        pension=PensionInput(
            provider=pension_raw.get("provider"),
            ee_contribution_shown=to_float(pension_raw.get("ee_contribution")),
            er_contribution_shown=to_float(pension_raw.get("er_contribution")),
            ytd_ee_pension=to_float(pension_raw.get("ytd_ee_pension")),
            ytd_er_pension=to_float(pension_raw.get("ytd_er_pension")),
        ),
        summary=PayslipSummaryFigures(
            total_gross_pay=to_float(summary_raw.get("total_gross_pay")),
            gross_for_tax=to_float(summary_raw.get("gross_for_tax")),
            earnings_for_ni=to_float(summary_raw.get("earnings_for_ni")),
            tax_paid=to_float(summary_raw.get("tax_paid")),
            ni_paid=to_float(summary_raw.get("ni_paid")),
            net_pay=to_float(summary_raw.get("net_pay")),
        ),
        ytd=YTDFigures(
            ytd_gross=to_float(ytd_raw.get("ytd_gross")),
            ytd_gross_for_tax=to_float(ytd_raw.get("ytd_gross_for_tax")),
            ytd_tax_paid=to_float(ytd_raw.get("ytd_tax_paid")),
            ytd_ni_paid=to_float(ytd_raw.get("ytd_ni_paid")),
            ytd_earnings_for_ni=to_float(ytd_raw.get("ytd_earnings_for_ni")),
        ),
        user_answers=UserAnswers(
            pay_frequency=PayFrequency(
                user_answers_raw.get("pay_frequency", "unknown")
            ) if user_answers_raw.get("pay_frequency") in ("monthly","weekly","unknown")
              else PayFrequency.UNKNOWN,
            pension_provider=user_answers_raw.get("pension_provider"),
        ),
    )

    result = validate_payslip(payslip)
    session["validation_result"] = result_to_dict(result)

    return redirect(url_for("results"))


def result_to_dict(result) -> dict:
    """Convert ValidationResult to JSON-serialisable dict for session storage"""
    return {
        "gross_for_tax": result.gross_for_tax_calculated,
        "earnings_for_ni": result.earnings_for_ni_calculated,
        "tax_expected": result.tax_expected,
        "ee_ni_expected": result.ee_ni_expected,
        "er_ni_expected": result.er_ni_expected,
        "net_pay_expected": result.net_pay_expected,
        "tax_variance": result.tax_variance,
        "ee_ni_variance": result.ee_ni_variance,
        "net_pay_variance": result.net_pay_variance,
        "flags": [
            {
                "severity": f.severity.value,
                "element_code": f.element_code,
                "code": f.code,
                "message": f.message,
                "expected": f.expected,
                "actual": f.actual,
                "variance": f.variance,
            }
            for f in result.flags
        ],
        "tax_breakdown": {
            "tax_code": result.tax_breakdown.tax_code,
            "is_k_code": result.tax_breakdown.is_k_code,
            "is_emergency": result.tax_breakdown.is_emergency,
            "is_scottish": result.tax_breakdown.is_scottish,
            "free_pay_period": result.tax_breakdown.free_pay_period,
            "k_addition": result.tax_breakdown.k_addition,
            "ytd_gross_for_tax": result.tax_breakdown.ytd_gross_for_tax,
            "ytd_taxable": result.tax_breakdown.ytd_taxable,
            "ytd_taxable_rounded": result.tax_breakdown.ytd_taxable_rounded,
            "bands_applied": result.tax_breakdown.bands_applied,
            "ytd_tax_calculated": result.tax_breakdown.ytd_tax_calculated,
            "prior_period_tax": result.tax_breakdown.prior_period_tax,
            "tax_this_period": result.tax_breakdown.tax_this_period,
            "cap_applied": result.tax_breakdown.cap_applied,
        },
        "ni_breakdown": {
            "ni_category": result.ni_breakdown.ni_category,
            "gross_for_ni": result.ni_breakdown.gross_for_ni,
            "bands_applied": result.ni_breakdown.bands_applied,
            "ee_ni_calculated": result.ni_breakdown.ee_ni_calculated,
            "er_ni_calculated": result.ni_breakdown.er_ni_calculated,
            "sage_uel_display": result.ni_breakdown.sage_uel_display,
        },
        "pension": {
            "type": result.pension_breakdown.pension_type.value if result.pension_breakdown else None,
            "basis": result.pension_breakdown.pension_basis.value if result.pension_breakdown else None,
            "pensionable_pay": result.pension_breakdown.pensionable_pay if result.pension_breakdown else None,
            "ee_expected": result.pension_breakdown.ee_contribution_expected if result.pension_breakdown else None,
            "er_expected": result.pension_breakdown.er_contribution_expected if result.pension_breakdown else None,
            "er_true": result.pension_breakdown.er_true_contribution if result.pension_breakdown else None,
            "tpr_total_met": result.pension_breakdown.tpr_total_met if result.pension_breakdown else None,
        },
        "pay_frequency": result.pay_frequency_confirmed.value,
        "tax_year": result.tax_year_confirmed.value,
    }


# ---------------------------------------------------------------------------
# RESULTS
# ---------------------------------------------------------------------------

@app.route("/results")
def results():
    if "validation_result" not in session:
        return redirect(url_for("upload"))

    result = session["validation_result"]
    payslip_data = session.get("payslip_data", {})

    return render_template(
        "results.html",
        result=result,
        payslip_data=payslip_data,
    )


# ---------------------------------------------------------------------------
# CONTACTS PAGE
# ---------------------------------------------------------------------------

@app.route("/contacts")
def contacts():
    return render_template("contacts.html")


if __name__ == "__main__":
    app.run(debug=True)
