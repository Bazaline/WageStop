"""
Wagestop — Payslip OCR and Classification Engine
Option C: pdfplumber for clean PDFs, Claude vision API for images/unclear PDFs.
Extracts all pay lines, metadata, and summary figures from uploaded payslips.
"""

import re
import json
import os
import base64
import anthropic
from typing import Optional
from pathlib import Path

try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

from .elements import classify_pay_lines, ELEMENT_CATEGORIES


def get_client():
    """Get Anthropic client with explicit API key from environment"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Please add it in Render → Environment Variables."
        )
    return anthropic.Anthropic(api_key=api_key)


# ---------------------------------------------------------------------------
# CLAUDE VISION EXTRACTION
# ---------------------------------------------------------------------------

PAYSLIP_EXTRACTION_PROMPT = """You are a UK payroll expert reading a payslip image.
Extract ALL data from this payslip and return it as JSON only — no other text.

Return this exact structure:
{
  "software": "Sage 50 Desktop|BrightPay|Pento|Unknown",
  "payment_date": "YYYY-MM-DD",
  "tax_code": "1257L",
  "ni_category": "A",
  "pay_frequency": "monthly|weekly",
  "tax_period": 1,
  "pay_lines": [
    {
      "description": "Salary",
      "amount": 2500.00,
      "units": 1.0,
      "rate": 2500.0
    }
  ],
  "deduction_lines": [
    {
      "description": "PAYE Tax",
      "amount": 250.00
    }
  ],
  "pension": {
    "provider": null,
    "ee_contribution": null,
    "er_contribution": null,
    "ytd_ee_pension": null,
    "ytd_er_pension": null
  },
  "summary": {
    "total_gross_pay": null,
    "gross_for_tax": null,
    "earnings_for_ni": null,
    "tax_paid": null,
    "ni_paid": null,
    "net_pay": null
  },
  "ytd": {
    "ytd_gross": null,
    "ytd_gross_for_tax": null,
    "ytd_tax_paid": null,
    "ytd_ni_paid": null,
    "ytd_earnings_for_ni": null
  }
}

Rules:
- payment_date: use the payment/process date shown, NOT the pay period
- pay_lines: payments only (positive amounts)
- deduction_lines: deductions only (negative/deducted amounts, return as positive)
- Salary sacrifice: include as a pay_line with a negative amount
- employer_ni and employer_pension go in deduction_lines
- Return null for any field not shown on the payslip
- NEVER invent or estimate figures — only extract what is clearly visible
- Do not include employee name, NI number, or home address"""


def encode_image(file_path: str) -> tuple[str, str]:
    """Encode image file to base64. Returns (base64_data, media_type)"""
    path = Path(file_path)
    suffix = path.suffix.lower()
    media_types = {
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png":  "image/png",
        ".gif":  "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_types.get(suffix, "image/jpeg")
    with open(file_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, media_type


def extract_with_claude_vision(file_path: str) -> dict:
    """
    Send payslip image or PDF to Claude vision API for extraction.
    Returns structured dict of payslip data.
    """
    client = get_client()
    path = Path(file_path)

    if path.suffix.lower() == ".pdf":
        # Send PDF as document
        with open(file_path, "rb") as f:
            pdf_data = base64.standard_b64encode(f.read()).decode("utf-8")
        content = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": pdf_data,
                }
            },
            {"type": "text", "text": PAYSLIP_EXTRACTION_PROMPT}
        ]
    else:
        # Send as image
        img_data, media_type = encode_image(file_path)
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": img_data,
                }
            },
            {"type": "text", "text": PAYSLIP_EXTRACTION_PROMPT}
        ]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": content}]
    )

    raw_text = response.content[0].text.strip()

    # Strip any markdown code fences if present
    raw_text = re.sub(r"^```json\s*", "", raw_text)
    raw_text = re.sub(r"\s*```$", "", raw_text)

    return json.loads(raw_text)


# ---------------------------------------------------------------------------
# PDF TEXT EXTRACTION (pdfplumber — clean PDFs only)
# ---------------------------------------------------------------------------

def extract_with_pdfplumber(file_path: str) -> Optional[dict]:
    """
    Attempt text extraction from a clean PDF using pdfplumber.
    Returns None if extraction produces insufficient data (fall back to Claude).
    """
    if not PDF_AVAILABLE:
        return None

    try:
        with pdfplumber.open(file_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""

        if len(text.strip()) < 50:
            # Not enough text — likely a scanned/image PDF
            return None

        # Basic quality check — must find monetary amounts
        if not re.search(r"£?\d+\.\d{2}", text):
            return None

        # pdfplumber extracted usable text — pass to Claude for structured parsing
        # (Claude still does the classification, pdfplumber just confirms it's a text PDF)
        return {"raw_text": text, "source": "pdfplumber"}

    except Exception:
        return None


# ---------------------------------------------------------------------------
# MAIN EXTRACTION ORCHESTRATOR (Option C)
# ---------------------------------------------------------------------------

def extract_payslip_data(file_path: str) -> dict:
    """
    Main extraction function — Option C:
    1. Try pdfplumber for clean PDFs
    2. Fall back to Claude vision for images or unclear PDFs

    Returns structured payslip dict ready for classification.
    """
    path = Path(file_path)
    extraction_method = "claude_vision"

    if path.suffix.lower() == ".pdf":
        pdf_result = extract_with_pdfplumber(file_path)
        if pdf_result and pdf_result.get("raw_text"):
            # PDF has extractable text — use Claude with text content
            extraction_method = "pdfplumber+claude"
            extracted = extract_with_claude_text(pdf_result["raw_text"])
        else:
            # Scanned/image PDF — use Claude vision
            extracted = extract_with_claude_vision(file_path)
    else:
        # Image file — use Claude vision directly
        extracted = extract_with_claude_vision(file_path)

    extracted["_extraction_method"] = extraction_method
    return extracted


def extract_with_claude_text(raw_text: str) -> dict:
    """
    Send extracted PDF text to Claude for structured parsing.
    Used when pdfplumber successfully extracts text from a clean PDF.
    """
    client = get_client()

    prompt = f"""You are a UK payroll expert. Parse this payslip text and return JSON only.

{PAYSLIP_EXTRACTION_PROMPT}

Payslip text:
{raw_text}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw_response = response.content[0].text.strip()
    raw_response = re.sub(r"^```json\s*", "", raw_response)
    raw_response = re.sub(r"\s*```$", "", raw_response)

    return json.loads(raw_response)


# ---------------------------------------------------------------------------
# BUILD PAYSLIP INPUT FROM EXTRACTION
# ---------------------------------------------------------------------------

def build_payslip_input_from_extraction(extracted: dict) -> dict:
    """
    Convert raw extraction dict to structured format ready for
    the PayslipInput model and user review screen.
    Groups lines by category and classifies element codes.
    """
    # Combine pay lines and deductions into one list for classification
    raw_lines = []

    for line in extracted.get("pay_lines", []):
        raw_lines.append({
            "description": line.get("description", ""),
            "amount": float(line.get("amount", 0)),
            "units": line.get("units"),
            "rate": line.get("rate"),
            "line_type": "payment",
        })

    for line in extracted.get("deduction_lines", []):
        raw_lines.append({
            "description": line.get("description", ""),
            "amount": float(line.get("amount", 0)),
            "units": None,
            "rate": None,
            "line_type": "deduction",
        })

    # Classify all lines
    classified_lines = classify_pay_lines(raw_lines)

    # Group by category for review screen
    grouped = {cat: [] for cat in ELEMENT_CATEGORIES.keys()}
    grouped["Other"] = []

    for line in classified_lines:
        cat = line.get("category", "Other")
        grouped.setdefault(cat, []).append(line)

    def fmt(val):
        """Round to 2dp, return empty string if None"""
        try:
            return round(float(val), 2) if val is not None else None
        except (ValueError, TypeError):
            return val

    # Round pension values
    raw_pension = extracted.get("pension", {})
    pension = {k: fmt(v) if isinstance(v, (int, float, str)) else v
               for k, v in raw_pension.items()}

    # Round summary values
    raw_summary = extracted.get("summary", {})
    summary = {k: fmt(v) if isinstance(v, (int, float, str)) else v
               for k, v in raw_summary.items()}

    return {
        "metadata": {
            "software": extracted.get("software"),
            "payment_date": extracted.get("payment_date"),
            "tax_code": extracted.get("tax_code"),
            "ni_category": extracted.get("ni_category", "A"),
            "pay_frequency": extracted.get("pay_frequency", "monthly"),
            "tax_period": extracted.get("tax_period"),
        },
        "grouped_lines": grouped,
        "all_lines": classified_lines,
        "pension": pension,
        "summary": summary,
        "ytd": extracted.get("ytd", {}),
        "extraction_method": extracted.get("_extraction_method"),
    }
