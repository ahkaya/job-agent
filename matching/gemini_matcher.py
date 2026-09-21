import json
import os
from datetime import datetime

import yaml
from google import genai


PROFILE_PATH = "config/master_profile.yaml"
RULES_PATH = "config/matching_rules.yaml"


def load_matching_config():

    with open(
        PROFILE_PATH,
        "r",
        encoding="utf-8",
    ) as file:
        master_profile = yaml.safe_load(file)

    with open(
        RULES_PATH,
        "r",
        encoding="utf-8",
    ) as file:
        matching_rules = yaml.safe_load(file)

    return master_profile, matching_rules


def calculate_days_old(posted_date):

    if not posted_date:
        return None

    try:

        posted = datetime.strptime(
            posted_date,
            "%Y-%m-%d",
        ).date()

        today = datetime.now().date()

        days_old = (
            today - posted
        ).days

        if days_old < 0:
            return None

        return days_old

    except ValueError:

        return None


def build_matching_prompt(
    job,
    master_profile,
    matching_rules,
):

    job_description = (
        job.get("job_description", "")
        or job.get("description", "")
    )

    prompt = f"""
You are a job-matching assistant.

Compare ONE job description against the candidate's Master Profile
and Matching Rules.

The Master Profile is the ONLY source of truth about the candidate.

STRICT DATA INTEGRITY:
- Never invent or assume skills, responsibilities, achievements,
  metrics, dates, education, certifications, tools or experience.
- Never upgrade a skill level.
- Never turn academic experience into professional industry experience.
- Never turn a founding-partner period into equivalent full-time employment.
- For Taymada Cosmetics & MQLE Cosmetics, involvement varied during
  2021-2025 and must not be described as four years of continuous
  full-time employment.
- Do not count every responsibility under a job as four years of experience.
- If evidence is insufficient, mark it appropriately.

MATCHING:
Evaluate primarily:
1. Core responsibilities
2. Required skills/tools
3. Qualifications
4. Transferable experience
5. Language requirements
6. Education compatibility

For important requirements classify evidence as:
- Direct Match
- Transferable Match
- Gap
- Not stated

EXPERIENCE:
- Years of experience are not automatic rejection criteria.
- Do not inflate experience.
- Compare requested experience with relevant verified evidence.
- Academic experience must remain clearly academic.
- Do not convert education into professional work experience.
- Do not convert general background into direct professional experience
  in a specific function, industry, software or process.
- If evidence is insufficient, state the limitation.

MATCH CATEGORY:
Use exactly one:
- Strong Match
- Potential Match
- Low Relevance

Strong Match requires substantial direct evidence across the job's
core responsibilities and important requirements.

Do not assign Strong Match solely because the job title belongs to
a priority job family or because the candidate has a relevant degree.

When evidence is limited, prefer Potential Match rather than making
unsupported assumptions.

LANGUAGE:
Follow the Matching Rules exactly.
Do not treat A1/A2 Dutch as fluent or professional Dutch.

SALARY:
Salary must never affect Match Category.

IMPORTANT:
The job metadata below is authoritative.
Do not change or infer:
- job_title
- company
- location
- posted_date

CANDIDATE MASTER PROFILE:
{yaml.dump(
    master_profile,
    allow_unicode=True,
    sort_keys=False,
)}

MATCHING RULES:
{yaml.dump(
    matching_rules,
    allow_unicode=True,
    sort_keys=False,
)}

JOB METADATA:
{json.dumps(job, ensure_ascii=False, indent=2)}

JOB DESCRIPTION:
{job_description}

Return ONLY valid JSON.
Do not use Markdown.
Do not include ```json.
Do not add explanations outside the JSON.

Use exactly this structure:

{{
  "job_title": "",
  "company": "",
  "job_family": "",
  "seniority": "",
  "location": "",
  "country": "Netherlands",
  "work_model": "",
  "salary": "",
  "salary_period": "",
  "salary_type": "",
  "posted_date": "",
  "days_old": null,
  "key_requirements": [],
  "dutch_requirement": "",
  "education_requirement": "",
  "experience_requirement": "",
  "match_category": "",
  "why_match": [],
  "direct_matches": [],
  "transferable_matches": [],
  "gaps": [],
  "experience_gap": "",
  "education_match": "",
  "language_match": "",
  "priority": ""
}}

Rules for missing information:
- Use "" for unknown text fields.
- Use [] for empty lists.
- Use null for unknown numeric fields.
- Never guess missing information.
- Do not create a gap for a tool, qualification or requirement unless
  the job description actually mentions it or clearly implies it.
- If a requirement is not mentioned, use "Not stated" rather than Gap.
- Avoid unsupported phrases such as "fully satisfies", "meets or exceeds",
  "no experience gap", or "strong educational alignment".
"""

    return prompt


def analyze_job(job):

    master_profile, matching_rules = (
        load_matching_config()
    )

    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"]
    )

    prompt = build_matching_prompt(
        job,
        master_profile,
        matching_rules,
    )

    interaction = client.interactions.create(
        model="gemini-3.6-flash",
        input=prompt,
    )

    raw_response = (
        interaction.output_text.strip()
    )

    try:

        analysis = json.loads(
            raw_response
        )

    except json.JSONDecodeError as error:

        raise ValueError(
            "Gemini did not return valid JSON."
        ) from error

    return analysis