# Python Data Quality Checker

Automated **Source vs Target** data quality validation for Google BigQuery.

The script compares source and target tables and checks for:

| Check                | What it does                                             |
| -------------------- | -------------------------------------------------------- |
| **Nulls**      | Checks critical columns for null values (with threshold) |
| **Duplicates** | Detects duplicate rows based on primary / business keys  |
| **Row Count**  | Compares number of rows between source and target tables |

If any check fails, it automatically sends a clean HTML email alert.

---

## Project Structure

```
data_quality_checker/
├── main.py                     # Entry point
├── requirements.txt
├── .env.example                # Template for secrets
├── .gitignore
├── config/
│   └── config.example.yaml     # Template → copy to config.yaml
├── src/
│   ├── checker.py              # Core data quality logic
│   └── alerter.py              # Email notification
├── sample_data/                # Example CSVs with intentional issues
└── logs/                       # Auto-created log files
```

---

## Prerequisites

- Python 3.9 or higher
- A Google Cloud project with BigQuery enabled
- A **Service Account** JSON key with these roles:
  - `BigQuery Job User`
  - `BigQuery Data Viewer`
- (Optional) Gmail account with **App Password** for email alerts

---

## Quick Start

### 1. Create virtual environment & install packages

**Windows**

```powershell
cd data_quality_checker
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Linux / Mac**

```bash
cd data_quality_checker
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Set up credentials (`.env`)

```bash
cp .env.example .env
```

Edit `.env`:

```env
GOOGLE_APPLICATION_CREDENTIALS=D:\full\path\to\your-service-account-key.json
EMAIL_PASSWORD=your_16_char_gmail_app_password
```

> **Important**
>
> - Use the **full absolute path** to the JSON key
> - For Gmail, create an **App Password** (Google Account → Security → App passwords)
> - Do **not** use your normal Gmail password

### 3. Configure tables & email (`config.yaml`)

```bash
cp config/config.example.yaml config/config.yaml
```

Edit `config/config.yaml`:

```yaml
project_id: "your-gcp-project-id"

tables:
  - name: "Orders"
    source: "raw_dataset.Orders"
    target: "curated_dataset.Orders"
    primary_keys: ["order_id"]
    critical_columns: ["order_id", "customer_id", "amount"]
    null_threshold_pct: 0.0          # 0.0 = any null fails

  - name: "Customers"
    source: "raw_dataset.Customers"
    target: "curated_dataset.Customers"
    primary_keys: ["customer_id"]
    critical_columns: ["customer_id", "email", "created_at"]
    null_threshold_pct: 0.5

email:
  enabled: true
  smtp_server: "smtp.gmail.com"
  smtp_port: 587
  sender: "your-email@gmail.com"
  password_env: "EMAIL_PASSWORD"     # must match the name in .env
  recipients:
    - "your-email@gmail.com"
  subject_prefix: "[Data Quality Alert]"
```

### 4. Run the checker

```powershell
python main.py
```

**Exit codes**

- `0` → All checks passed
- `1` → One or more checks failed (useful for CI / schedulers)

---

## How the Email Alert Works

- Email is sent **only when at least one check fails**
- Shows a clean summary grouped by table
- Contains only the failed checks (not the passed ones)
- Works with Gmail, Outlook, or any SMTP server

---

## Common Issues & Fixes

| Problem                                           | Solution                                                                                                 |
| ------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `ModuleNotFoundError: No module named 'yaml'`   | Run`pip install -r requirements.txt`                                                                   |
| `DefaultCredentialsError`                       | Check the path in`.env` and set `$env:GOOGLE_APPLICATION_CREDENTIALS` in PowerShell                  |
| `Not found: Project ...`                        | Project ID in`config.yaml` must match the project of your service account key                          |
| `UnicodeEncodeError` (arrows)                   | Already fixed – all special characters removed                                                          |
| `bigquery.readsessions.create` permission error | Do**not** install `google-cloud-bigquery-storage` unless the service account has that permission |
| Email not sent                                    | Make sure`EMAIL_PASSWORD` is set in `.env` **and** in the current terminal session             |

---
