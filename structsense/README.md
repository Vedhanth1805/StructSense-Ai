# StructSense AI

Structural risk assessment and research decision support. The repository keeps its existing Streamlit demonstration and PPO/Gymnasium, risk scoring, Neural DSW, document, plotting, and ReportLab modules, and adds a persistent Django API that organizes the implementation into exactly four logical services:

1. **Web & Data** — Django REST Framework, authentication, project/document/analysis history, parameter corrections, and audit events.
2. **Document & BIM** — PyMuPDF extraction, Tesseract fallback for pages with little text, optional Groq mapping, IFC ingestion through IfcOpenShell, source fusion, and conflicts.
3. **AI & Structural Analysis** — existing Gymnasium stress checks, PPO agent, Neural DSW, rule checks, and risk scoring.
4. **Reporting & Visualization** — existing PDF/CSV outputs and risk plots, parametric frame geometry, and an exportable structural risk demo video. The frame is illustrative and is not FEA.

This is a decision-support/research prototype. Outputs do not replace professional engineering judgement, statutory approval, formal design verification, or a validated finite-element analysis.

## Local setup

Use Python 3.11–3.14 where supported by the selected PyTorch / IfcOpenShell wheels. From `structsense/`:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

For PDF OCR on macOS with Homebrew, install the system executable with `brew install tesseract`; on other systems, install Tesseract using that OS's package manager and make sure `tesseract --version` works in the same shell that starts Django. OCR runs only on pages with insufficient extracted text; if the executable is absent, the page records `tesseract_unavailable` and the project UI reports the limitation without fabricating parameters. IFC support has separate platform-dependent wheels; install it with `python -m pip install -r requirements-ifc.txt` when your Python/OS combination has a compatible IfcOpenShell wheel.

Configure `DJANGO_SECRET_KEY`, `DATABASE_URL`, and `STRUCTSENSE_REQUIRE_POSTGRESQL=true` in the ignored local `.env`. PostgreSQL is used when `DATABASE_URL` is a valid `postgresql://` URL; the require flag makes Django stop at startup if that URL is missing instead of falling back to SQLite. An unsupported non-empty URL also fails at startup. For an intentionally separate SQLite development run only, set `STRUCTSENSE_REQUIRE_POSTGRESQL=false` and `DATABASE_URL=`. Never put the database password in source, reports, or committed configuration. The browser app is at `http://127.0.0.1:8000/`; create the local tables and an account:

```bash
cd backend
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### PostgreSQL development setup

Provision a local database and login role using a PostgreSQL administrator account. The following `psql` commands inspect the existing roles/databases; create only what is missing:

```sql
\du
\l
CREATE ROLE structsense LOGIN;
\password structsense
CREATE DATABASE structsense OWNER structsense;
```

The `\password` command prompts locally and avoids putting the new role password in SQL history. Put the connection URL in the ignored local `.env` file as `DATABASE_URL=postgresql://structsense:<URL-encoded-password>@127.0.0.1:5432/structsense`; replace the placeholder locally and never commit or paste the credential. Keep `STRUCTSENSE_REQUIRE_POSTGRESQL=true` for the demo environment. Then from `backend/`, run `python manage.py migrate`, `python manage.py check`, and `python manage.py showmigrations`. Confirm the active backend with `python manage.py shell -c 'from django.db import connection; connection.ensure_connection(); print(connection.vendor)'`; PostgreSQL must print `postgresql`. SQLite is available only when the require flag is explicitly disabled and `DATABASE_URL` is blank.

Document review shows an interpretation label for each processed file. When a key is absent, the app labels extraction `LOCAL / RULE-BASED FALLBACK`; with a key, Groq/LLaMA is called only when explicitly matched extraction leaves supported values missing. The stored extraction metadata distinguishes a successful live request, a failed request with local fallback, and a request that was not needed. Enable live Groq interpretation by setting `GROQ_API_KEY` in the ignored local `.env`, restarting Django, and processing a document that has supported values not captured by explicit patterns. No live response is claimed until a request succeeds. Never commit `.env` or include the key in logs or screenshots.

### OCR system dependency

Python's `pytesseract` package is only a wrapper; the Tesseract executable must also be installed and available on `PATH`. On macOS with Homebrew, install it with `brew install tesseract`, then verify with `tesseract --version`. Confirm the project fallback and fixture with:

```bash
python -c 'from document_intelligence.pdf_ingester import PDFIngester; r=PDFIngester().extract_text_from_pdf("data/demo-structural-scanned.pdf"); print(r.get("extraction_quality"), [(p["method"], p["char_count"]) for p in r.get("pages", [])])'
```

Expected success reports `tesseract` and nonzero extracted characters; when the executable is missing, the app records `tesseract_unavailable`, extracts no invented values, and shows a warning in the project page.

### Seed the presentation project

The Django app includes a reproducible local demo setup. With the virtual environment active and `.env` configured for the database you intend to use (PostgreSQL for the full demo), run:

```bash
cd backend
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
```

`seed_demo` creates the `StructSense AI Major Project Demo` project, two searchable PDFs (M30 and M25, producing an engineer-review conflict), 18 sourced parameters, a resolved correction, base and modified analyses, and audit history in the configured database. The base analysis runs the existing PPO and Neural DSW; the modified run executes all five existing checks. On first creation, the command prints a generated demo login password. Set `STRUCTSENSE_DEMO_USERNAME` and `STRUCTSENSE_DEMO_PASSWORD` before running the command to choose credentials. Re-running it does not reset an existing password or duplicate the seeded documents and analyses. Do not blank `DATABASE_URL` unless you intentionally want a separate SQLite development database.

An actual minimal IFC sample is also included at [`data/demo-structural-frame.ifc`](data/demo-structural-frame.ifc). Upload it from the project page to exercise IFC element/property ingestion. The generated presentation fallback is available at [`demo-output/structsense-structural-risk-demo.gif`](demo-output/structsense-structural-risk-demo.gif).

For a local database created by an earlier version with `migrate --run-syncdb`, run `python manage.py migrate --fake-initial` once so Django adopts those tables and applies the added parameter-metadata migration.

The API is under `http://127.0.0.1:8000/api/`; endpoints require Django session or HTTP Basic authentication. Sign in through `/accounts/login/`; create users through Django admin at `/admin/` or use `createsuperuser`. Uploaded files are stored under a private media directory and are not exposed through a public media URL.

Successful Django logins are recorded as global `login` audit events without credentials or session data. Project-scoped events record uploads/processing, parameter review and corrections, conflict resolution, analysis and scenario runs, comparisons, report generation, exports, and video generation. The records are stored in PostgreSQL.

### Generate the presentation demo

Open any project while signed in and select **Generate demo video (MP4 or GIF)**, or submit a CSRF-protected POST to `/projects/{id}/demo-video/` from that session. The fixed reproducible demo uses values from the project's supported 18-parameter schema, displays each parameter change beside the updated 3D columns, beams, and slabs, and sends both the original and modified configurations through the existing analysis service and risk scorer. The download is stored under the private media directory and served only through the authenticated project action.

When system FFmpeg or the `imageio-ffmpeg` bundled binary is installed and can encode H.264, the action exports MP4. Each of the 13 presentation scenes is held for four seconds (about 52 seconds total) so the parameter values and analysis output can be read. If neither encoder is available or H.264 encoding fails, it exports an animated GIF with the same scene timing that can be inserted into a presentation or converted to video. The animation is an illustrative parametric visualization: it does not simulate bending, cracking, or other deformation and is not FEA. Analysis output remains the existing simplified research screening, not formal design verification.

### API workflow

- `POST /api/projects/` with `name`, optional `description`
- `POST /api/projects/{id}/documents/` multipart field `file` (PDF or IFC, max 50 MB)
- `POST /api/documents/{id}/process/`
- `GET /api/projects/{id}/parameters/` to inspect source, extraction method, confidence, and conflicts
- `POST /api/projects/{id}/review/` with `{"parameters":{"concrete_grade":{"action":"confirm"},"beam_depth_mm":{"action":"correct","value":450,"reason":"verified drawing"}}}`; engineer-entered fields use `action=correct`
- `POST /api/projects/{id}/analyses/` to run all implemented scenarios, or include `scenario` as one of the scenario names / IDs 0–4. Add `include_ppo: true` to run the existing PPO training/evaluation plus NeuralDSW inference; training is optional because it takes longer. `ppo_timesteps` is bounded to 512–10000.
- `GET /api/projects/{id}/dashboard/`, `GET /api/projects/{id}/analyses/`, and `GET /api/projects/{id}/export.csv`
- `GET /api/projects/{id}/model/` returns the parametric illustrative frame geometry
- `POST /api/projects/{id}/compare/` with complete `configuration_a` and `configuration_b` objects runs and compares actual checks, risk scores, parameter differences, and illustrative models
- `POST /api/analyses/{uuid}/report/` generates and returns a PDF report
- `POST /projects/{id}/demo-video/` (signed-in browser session) generates the reproducible MP4/GIF demonstration

### Supported parameter schema

The document extractor, review form, API validation, analysis environment, and demo use this same 18-field schema. The ranges are those in `environment/building_env.py`; categorical values are encoded as shown.

| Parameter | Range / unit |
| --- | --- |
| `concrete_grade` | 15–60 MPa |
| `steel_grade` | 250–550 MPa |
| `column_width_mm`, `column_depth_mm` | 200–800 mm each |
| `num_floors` | 1–20, integer |
| `floor_load_kn_m2` | 2–15 kN/m² |
| `soil_bearing_capacity_kn_m2` | 50–500 kN/m² |
| `foundation_depth_m` | 0.5–5 m |
| `seismic_zone` | integer 1–5 |
| `wind_speed_kmph` | 20–250 km/h |
| `rainfall_mm_annual` | 200–3000 mm/year |
| `building_age_years` | 0–100 years |
| `shear_wall_present` | 0 or 1 |
| `foundation_type` | 0 isolated, 1 raft, 2 pile |
| `column_reinforcement_ratio` | 0.008–0.06 |
| `beam_depth_mm` | 300–900 mm |
| `slab_thickness_mm` | 100–300 mm |
| `location_risk_index` | 0–1 |

Analysis is blocked until all 18 parameters in the existing `PARAM_KEYS` schema have values and engineer validation status. The service runs the existing environment's five scenario checks and existing risk scorer; it does not claim to run FEA. Missing values are not filled with defaults during document extraction.

### PPO, Neural DSW, and scenarios

The Gymnasium observation is the existing 18-parameter vector normalized against `PARAM_BOUNDS`. The five discrete actions are normal occupancy, seismic, combined wind/rain, 150% overload, and long-term degradation checks. An action applies its existing simplified engineering check, updates damage/risk state, and returns Gymnasium's observation, reward, termination flags, and check details. With `include_ppo: true`, the shared NeuralDSW checkpoint is loaded before PPO training; its state-dependent output scales the environment's deterministic failure penalty by `(0.5 + DSW weight)`, neutral at a DSW output of 0.5. This makes DSW output an actual input to PPO's training and evaluation rewards, while retaining the existing environment heuristic and repeat-action penalty. The passed DSW weight is recorded in environment info and PPO training metrics. PPO remains a research policy over scenario actions, not a validated structural design optimizer.

The API runs the existing engineering checks and StructuralRiskScorer by default. Request `include_ppo: true` to train/evaluate the existing Stable-Baselines3 policy with NeuralDSW reward guidance. PPO training accepts 512–10,000 timesteps in the web form and API. NeuralDSW uses a shared checkpoint at `outputs/models/neural_dsw.pt` (override with `STRUCTSENSE_DSW_CHECKPOINT`): the first request trains once on bundled synthetic targets and atomically saves the weights; later requests in the same process reuse that model, and a restarted process loads the checkpoint. Its labels are 1 when the current aggregate score is at least 0.55 and 0 otherwise, trained with Adam and binary cross-entropy. It remains a learned approximation of that threshold, trained independently of PPO rollouts and not calibrated against field outcomes. During PPO runs its output now enters the environment reward as described above. The aggregate score is `0.50 × legacy six-factor risk + 0.50 × mean(foundation, columns, beams, slab risks)`. This screening formula is versioned as `six-factor-plus-element-mean-v1`; pre-existing analysis records retain their original historical scores and do not get silently recalculated.

The supported scenario IDs are 0–4 as listed above. A scenario-specific API analysis evaluates that one check; omitting `scenario` runs all five independently against the same validated input. `POST /api/projects/{id}/compare/` compares two full parameter configurations by running the same implemented analysis on each and returning risk results and visualization geometry.

### Paper benchmark availability

The original NH-48 source documents and evaluation labels/table are not present in this repository or available Git history, so no NH-48 paper result is claimed. A data-driven JSONL evaluation harness is provided in [`evaluation/README.md`](evaluation/README.md). It runs the existing PDF extraction path against user-supplied ground truth and reports extraction accuracy and coverage; the demo PDFs remain separate and are not presented as NH-48 benchmark data.

## Existing Streamlit demonstration

From `structsense/` after installing dependencies:

```bash
python -m streamlit run app.py
```

The Streamlit UI remains available for the existing interactive PPO research demonstration. Its session-based workflow is separate from the persistent Django API.

## Data and limitations

- PDF extraction is text-first; OCR is a page-level fallback. Tesseract executable availability is an OS setup requirement.
- Extracted parameter records keep the schema unit, source document, extraction method, confidence type, and matched PDF page location when available. Missing and unsupported values stay unavailable.
- IFC properties vary by model authoring tool. Only properties actually present are emitted; unsupported/missing values remain unavailable.
- Extraction confidence is labeled as an extraction score, not a calibrated probability.
- Multiple source values are retained and marked for engineer review rather than silently overwritten.
- Existing engineering checks are simplified prototype calculations. Treat results as research output and have qualified engineers verify inputs and conclusions.
- IFC wheel installation and PostgreSQL service setup are platform-dependent.

## Tests

Run the core tests from the repository root with `python -m unittest discover -s structsense/tests -v`. Django integration tests can be run after dependencies are installed with `cd structsense/backend && python manage.py test webdata`. PostgreSQL, Tesseract, live Groq, and FFmpeg depend on separately installed services, system programs, or credentials; their status must be verified on the target machine. IFC support is optional and requires a compatible IfcOpenShell wheel.
