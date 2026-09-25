# job-agent

Personal job-search automation system that aggregates job postings from multiple
sources, matches them against a candidate profile using LLM APIs, generates
tailored CVs and cover letters, and tracks the full application lifecycle.

## Features

### Collection
- ATS platforms: Greenhouse, Lever, Ashby, SmartRecruiters, Workable, BambooHR,
  Workday, Breezy, Rippling, Teamtailor, Recruitee (11 total)
- Dutch recruitment agencies: Randstad, Tempo-Team, Adecco (public JSON APIs)
- Deterministic filtering: location, seniority, blacklist, relevance

### Matching
- LLM-based matching via GLM (Z.AI), parallel workers (5x speedup)
- Optional Gemini, NVIDIA, Ollama backends
- Match lifecycle tracking (current vs. invalidated matches)

### Documents
- LLM-tailored CV + cover letter for each job
- DOCX + PDF export (python-docx + dxpdf)
- Professional filenames (`2026-09-25_<Company>_<Position>_CV.pdf`)

### Dashboard (Streamlit)
- Job pool with filters (match category, priority, distance from Almelo)
- One-click CV generation
- **Apply with Autofill** button for Greenhouse/Lever/Ashby forms
  (Selenium + LLM, never auto-submits, opens Chrome for manual review)
- Application tracking with response status per job
- Manual job entry for LinkedIn/Indeed postings
- Response inbox with LLM-classified categories
  (interview / rejection / offer / info)

### Application tracking
- Companion repo: [job-agent-integrations](https://github.com/ahkaya/job-agent-integrations)
- Gmail -> Make.com -> Sheets -> Ansible on GitHub Actions -> LLM ->
  Turso cloud DB -> Telegram notifications
- Local dashboard and cloud pipeline share the same Turso DB via
  `pyturso` (local-first, automatic sync)

## Setup

### 1. Install dependencies

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

### 2. Configure environment

Copy `.env.example` to `.env` and fill in your API keys:

    cp .env.example .env

Required:
- `GLM_API_KEY` (Z.AI - matching, CV generation, response classification)

Optional:
- `GEMINI_API_KEY`
- `TAVILY_API_KEY` (web search discovery)
- `NVIDIA_API_KEY`
- `GOOGLE_SHEETS_ID` + `GOOGLE_SERVICE_ACCOUNT_JSON` (response tracking)
- `TURSO_SYNC_URL` + `TURSO_TOKEN` (cloud DB sync)

### 3. Configure candidate profile

Copy `config/master_profile.example.yaml` to `config/master_profile.yaml`
and fill in your details.

Copy `config/matching_rules.example.yaml` to `config/matching_rules.yaml`.

Copy `config/company_registry.example.yaml` to `config/company_registry.yaml`
with target companies.

### 4. Run

    python3 main.py                     # Collect + match
    streamlit run dashboard/app.py      # Dashboard

## Architecture

- `collectors/`    ATS + agency collectors
- `matching/`      LLM matchers (GLM, Gemini, NVIDIA, Ollama) + CV generation
- `dashboard/`     Streamlit UI (English)
- `data/`          SQLite layer with optional Turso cloud sync (pyturso)
- `config/`        Profile, rules, company registry
- `static/cv/`     Generated CV files (gitignored)

## Cloud sync

`data/database.py` uses `pyturso` to keep a local SQLite file in sync with a
Turso cloud database. When `TURSO_SYNC_URL` and `TURSO_TOKEN` are set, every
`commit()` is followed by a `push()`, and the dashboard calls `pull()` before
reading. Local and CI therefore see the same data.

## Related

- [job-agent-integrations](https://github.com/ahkaya/job-agent-integrations):
  SMTP applications, Selenium + LLM form filling, Gmail response tracking.

## License

MIT
