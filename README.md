# StructSense AI

> **AI-Powered Structural Failure Detection & Decision Support using PPO Reinforcement Learning**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.2+-success.svg)](https://www.djangoproject.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.40+-FF4B4B.svg)](https://streamlit.io/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.4+-EE4C2C.svg)](https://pytorch.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791.svg)](https://www.postgresql.org/)
[![Gymnasium](https://img.shields.io/badge/Gymnasium-1.0+-008080.svg)](https://gymnasium.farama.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

StructSense AI is an end-to-end structural risk assessment and decision-support platform designed to detect structural vulnerabilities early, audit design discrepancies across documents, and simulate failure modes using reinforcement learning and deterministic engineering standards (IS 456 / IS 1893).

The platform features both a persistent **Django REST Framework** multi-tenant web application backed by **PostgreSQL** and an interactive **Streamlit** research dashboard.

---

## 🏛️ System Architecture

The implementation is organized into four decoupled, production-grade services:

```
                                  STRUCTSENSE AI
                                         │
    ┌────────────────────┬───────────────┴───────────────┬────────────────────┐
    │                    │                               │                    │
┌───▼────────────┐ ┌─────▼───────────────┐ ┌─────────────▼──────┐ ┌───────────▼───────────┐
│  1. Web & Data │ │ 2. Document & BIM   │ │ 3. AI & Analysis   │ │ 4. Reporting & Viz    │
│  ───────────── │ │ ─────────────────── │ │ ────────────────── │ │ ───────────────────── │
│ • Django REST  │ │ • PyMuPDF text ext. │ │ • 18-dim Gym Env   │ │ • 3D Parametric Frame │
│ • PostgreSQL   │ │ • Tesseract OCR     │ │ • 5 Stress Checks  │ │ • ReportLab PDF Gen   │
│ • Full Audit   │ │ • IfcOpenShell BIM  │ │ • Neural DSW       │ │ • CSV Export          │
│ • History/Auth │ │ • M25/M30 Conflicts │ │ • PPO RL Agent     │ │ • 52s MP4/GIF Demo    │
│ • Corrections  │ │ • Groq/LLaMA (opt.) │ │ • Risk Scorer v1   │ │ • Interactive Plots   │
└────────────────┘ └─────────────────────┘ └────────────────────┘ └────────────────────────┘
```

1. **Web & Data Service** — Django REST Framework, authentication, session security, multi-tenant project management, parameter reviews, engineer correction audit logs, and PostgreSQL persistence.
2. **Document & BIM Intelligence** — PyMuPDF extraction, Tesseract OCR fallback, IfcOpenShell IFC element/property parsing, multi-source parameter fusion, and conflict detection (e.g. M25 vs M30 grade discrepancies).
3. **AI & Structural Analysis Service** — Custom 18-dimensional Gymnasium environment, IS 456 & IS 1893 deterministic engineering calculations across 5 stress scenarios, Neural DSW safety guidance, and Stable-Baselines3 PPO policy.
4. **Reporting & Visualization Service** — 3D parametric structural visualization (columns, beams, slabs), technical ReportLab PDF generation, CSV metadata export, and reproducible 52-second presentation MP4 / animated GIF generation.

---

## 🚀 Key Features

- **18-Parameter Structural Schema**: Rigorous bounds for concrete grade (15–60 MPa), steel grade (250–550 MPa), dimensions, loads, seismic zones, wind, rainfall, soil bearing capacity, foundation depth, and reinforcement ratios.
- **Traceable Ingestion & Multi-Source Fusion**: Extracts parameters from engineering drawings and IFC BIM models. Every extracted value retains exact document provenance, locator, extraction method, and confidence metric.
- **Conflict Detection & Engineer Review**: Detects cross-document discrepancies (such as conflicting concrete grades between specifications and structural drawings) and enforces human-in-the-loop validation before analyses can execute.
- **IS 456 / IS 1893 Stress Scenarios**:
  1. *Normal Occupancy Load Test*
  2. *Seismic Stress Test* (IS 1893 base-shear method)
  3. *Wind + Rain Combined Test*
  4. *Overload Test* (150% capacity)
  5. *Long-Term Degradation Test* (environmental aging)
- **Neural DSW + PPO Integration**: Neural DSW checkpoint scales the environment's failure penalty, feeding safety state directly into PPO reward optimization.
- **Demonstration Video & GIF Export**: Generates a reproducible 13-scene animated demonstration illustrating progressive structural variations, stress checks, and risk transitions.

---

## 📁 Repository Structure

```
.
├── README.md                              # Main project documentation
├── .gitignore                             # Global Git exclusion rules
└── structsense/                           # Main application package
    ├── app.py                             # Interactive Streamlit application
    ├── requirements.txt                   # Core Python dependencies
    ├── requirements-ifc.txt               # Optional IfcOpenShell dependencies
    ├── .env.example                       # Template for local environment variables
    ├── backend/                           # Django backend & API
    │   ├── manage.py
    │   ├── config/                        # Django project configuration & test settings
    │   └── webdata/                       # Web & Data app (models, views, API, templates)
    │       ├── models.py                  # PostgreSQL entities (Project, Document, AnalysisRun, etc.)
    │       ├── views.py                   # REST API and web endpoints
    │       ├── serializers.py             # DRF serializers
    │       └── management/commands/
    │           └── seed_demo.py           # Reproducible demo seeder
    ├── document_intelligence/             # Document extraction & BIM ingestion
    │   ├── pdf_ingester.py                # PyMuPDF text extraction + OCR fallback
    │   ├── ifc_ingester.py                # IfcOpenShell IFC parser
    │   ├── parameter_extractor.py         # Regex + optional Groq extraction
    │   └── fusion.py                      # Multi-source fusion & conflict detection
    ├── environment/                       # Reinforcement learning environment
    │   └── building_env.py                # 18-dim Gymnasium structural stress environment
    ├── risk/                              # Risk calculation & Neural DSW
    │   └── risk_module.py                 # StructuralRiskScorer & DSWCalculator
    ├── agent/                             # Reinforcement learning agents
    │   └── ppo_agent.py                   # PPO training & evaluation policy
    ├── analysis/                          # Analysis orchestration
    │   └── service.py                     # Unified structural analysis service
    ├── reporting/                         # Reporting and visualization
    │   ├── structure_model.py             # 3D parametric geometry generator
    │   ├── service.py                     # PDF & CSV reporting service
    │   └── demo_video.py                  # 52-second presentation MP4 / GIF exporter
    ├── data/                              # Sample data & test fixtures
    │   ├── demo-structural-scanned.pdf    # Sample structural drawing
    │   ├── demo-structural-frame.ifc      # Minimal valid IFC frame
    │   └── mock_report.txt                # Benchmark test input
    ├── demo-output/                       # Pre-generated presentation assets
    │   ├── structsense-structural-risk-demo.mp4
    │   └── structsense-structural-risk-demo.gif
    ├── evaluation/                        # Evaluation benchmarks
    │   ├── nh48_benchmark.py              # JSONL PDF extraction evaluation harness
    │   └── README.md
    └── tests/                             # Comprehensive test suite
        ├── test_core_workflow.py          # Extraction, fusion, and geometry tests
        ├── test_optional_integrations.py  # IFC, PDF, environment, and demo tests
        └── test_risk_scoring.py           # Aggregate formula and PPO/DSW tests
```

---

## 🛠️ Getting Started

### 1. Prerequisites
- **Python**: 3.11, 3.12, or 3.13 recommended.
- **PostgreSQL**: 14+ installed and running.
- **Tesseract OCR** *(Optional)*: `brew install tesseract` (macOS) or `apt-get install tesseract-ocr` (Linux).

### 2. Installation

Clone the repository and set up a virtual environment:

```bash
git clone https://github.com/Vedhanth1805/StructSense-Ai.git
cd StructSense-Ai/structsense

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

*(Optional: Install IfcOpenShell for BIM model processing)*:
```bash
pip install -r requirements-ifc.txt
```

### 3. Environment Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Configure your `.env` settings:
```ini
DJANGO_SECRET_KEY=your-secure-django-secret-key
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgresql://structsense:your_password@127.0.0.1:5432/structsense
STRUCTSENSE_REQUIRE_POSTGRESQL=true
STRUCTSENSE_DEMO_USERNAME=structsense-demo
STRUCTSENSE_DEMO_PASSWORD=StructSense-Demo-2026!
GROQ_API_KEY=                                      # Optional: add for live LLM extraction
```

### 4. Database Setup & Migrations

In PostgreSQL:
```sql
CREATE ROLE structsense WITH LOGIN PASSWORD 'your_password';
CREATE DATABASE structsense OWNER structsense;
```

Run migrations and seed the presentation demo data:
```bash
cd backend
python manage.py migrate
python manage.py seed_demo
```

---

## 🖥️ Running the Application

### Option A: Django Web Application & REST API
```bash
cd structsense/backend
python manage.py runserver 127.0.0.1:8000
```
- Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser.
- Sign in with username `structsense-demo` and the password configured above.
- REST API is available at [http://127.0.0.1:8000/api/](http://127.0.0.1:8000/api/).

### Option B: Interactive Streamlit Dashboard
```bash
cd structsense
python -m streamlit run app.py
```
- Open [http://127.0.0.1:8501/](http://127.0.0.1:8501/) to explore real-time RL stress tests and 3D parameter visualizers.

---

## 🧪 Running Tests

The test suite validates the entire pipeline without requiring mock data or external network access:

```bash
cd structsense

# 1. Run Core & Risk Scoring Tests (22 tests)
python -m unittest discover -s tests -v

# 2. Run Django Web & API Integration Tests (8 tests)
python backend/manage.py test webdata --settings=config.test_settings -v 2
```

**Test Coverage Summary: 30 passed, 0 failed, 0 errors.**

---

## 📡 REST API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/projects/` | `GET`, `POST` | List projects or create a new structural project |
| `/api/projects/{id}/documents/` | `POST` | Upload PDF or IFC file (up to 50 MB) |
| `/api/documents/{id}/process/` | `POST` | Ingest document and extract structural parameters |
| `/api/projects/{id}/parameters/` | `GET` | Retrieve extracted parameters, provenance, and conflicts |
| `/api/projects/{id}/review/` | `POST` | Submit engineer parameter confirmations or corrections |
| `/api/projects/{id}/analyses/` | `POST` | Execute 5 scenario checks, risk scoring, and optional PPO |
| `/api/projects/{id}/model/` | `GET` | Get 3D parametric column/beam/slab wireframe coordinates |
| `/api/projects/{id}/compare/` | `POST` | Compare base and modified structural configurations |
| `/api/analyses/{uuid}/report/` | `POST` | Generate and download formal technical PDF report |
| `/api/projects/{id}/export.csv` | `GET` | Export parameter and review history to CSV |
| `/projects/{id}/demo-video/` | `POST` | Render and download 52-second MP4/GIF presentation |

---

## ⚖️ Research Disclaimer

StructSense AI is a **decision-support and research prototype**.
- The structural calculations are based on simplified implementations of IS 456 / IS 1893 criteria for screening purposes.
- Outputs do not replace professional civil/structural engineering judgement, statutory building code compliance, physical inspection, or detailed Finite Element Analysis (FEA).

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
