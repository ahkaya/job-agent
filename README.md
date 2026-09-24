# job-agent

Personal job-search automation system that aggregates job postings from multiple sources, matches them against a candidate profile using LLM APIs, and generates tailored CVs and cover letters.

## Features

- Multi-source job collection:
  - ATS platforms: Greenhouse, Lever, Ashby, SmartRecruiters, Workable, BambooHR, Workday, Breezy, Rippling
  - Dutch recruitment agencies: Randstad, Tempo-Team, Adecco (JSON API)
- Deterministic filtering: location, seniority, blacklist, relevance
- LLM-based matching: GLM (Z.AI) with parallel workers (5x speedup)
- CV + cover letter generation: tailored to each job, DOCX + PDF export
- Streamlit dashboard:
  - Job pool with filters (match category, priority, distance)
  - CV generation with one click
  - Application tracking (applied/rejected)
  - Manual job entry for LinkedIn/Indeed postings

## Setup

### 1. Install dependencies

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

### 2. Configure environment

Copy `.env.example` to `.env` and fill in your API keys:

    cp .env.example .env

Required:
- GLM_API_KEY (Z.AI - for matching and CV generation)
- GEMINI_API_KEY (optional)
- TAVILY_API_KEY (optional - web search discovery)
- NVIDIA_API_KEY (optional)

### 3. Configure candidate profile

Copy `config/master_profile.example.yaml` to `config/master_profile.yaml` and fill in your details.
Copy `config/matching_rules.example.yaml` to `config/matching_rules.yaml`.
Copy `config/company_registry.example.yaml` to `config/company_registry.yaml` with target companies.

### 4. Run

    python3 main.py                     # Collect + match
    streamlit run dashboard/app.py      # Dashboard

## Architecture

- collectors/    ATS + agency collectors
- matching/      LLM matchers (GLM, Gemini, NVIDIA, Ollama)
- dashboard/     Streamlit UI
- data/          SQLite database layer
- config/        Profile, rules, company registry
- static/cv/     Generated CV files (gitignored)

## License

MIT
