# Wagestop

UK payslip validation web application.

## What it does
- Reads payslips via PDF upload or image (JPG, PNG etc.)
- Extracts and classifies all pay elements
- Validates tax, NI and pension calculations
- Flags errors with plain-English explanations
- Drill-down breakdown for each calculation

## Tech Stack
- **Backend:** Python / Flask
- **OCR:** pdfplumber (clean PDFs) + Claude API (images / scanned PDFs)
- **Frontend:** HTML / CSS / Vanilla JS
- **Hosting:** Render

---

## Deployment to Render

### Step 1 — Create a GitHub repository
1. Go to https://github.com and create a new repository called `wagestop`
2. Upload all files from this folder to the repository

### Step 2 — Create a Render account
1. Go to https://render.com and sign up (free)
2. Click **New +** → **Web Service**
3. Connect your GitHub account and select the `wagestop` repository

### Step 3 — Configure the service
Render will detect `render.yaml` automatically. You just need to add one environment variable manually:

| Key | Value |
|-----|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key from https://console.anthropic.com |

### Step 4 — Deploy
Click **Create Web Service**. Render will build and deploy automatically.
Your site will be live at `https://wagestop.onrender.com` (or similar).

---

## Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export ANTHROPIC_API_KEY=your_key_here
export SECRET_KEY=any-random-string

# Run
python app.py
```

Then open http://localhost:5000

---

## Project Structure

```
wagestop/
├── app.py                    Flask application
├── requirements.txt          Python dependencies
├── render.yaml               Render deployment config
├── validation/
│   ├── models.py             Data structures
│   ├── tax.py                Tax calculation engine
│   ├── ni.py                 NI calculation engine
│   ├── pension.py            Pension calculation engine
│   ├── elements.py           Pay element classifier
│   ├── payslip_reader.py     OCR engine
│   └── validator.py          Main orchestrator
├── templates/                HTML pages
└── static/                   CSS and JS
```
