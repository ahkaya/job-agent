import sys
import json
import os
import yaml
from google import genai

from data.database import get_connection, create_tables, find_duplicate_job
from data.job_input import is_within_30_days
from collectors.manual_collector import collect_manual_job

# --------------------------------------------------
# LOAD CONFIGURATION
# --------------------------------------------------

with open("config/master_profile.yaml", "r", encoding="utf-8") as f:
    master_profile = yaml.safe_load(f)

with open("config/matching_rules.yaml", "r", encoding="utf-8") as f:
    matching_rules = yaml.safe_load(f)


# --------------------------------------------------
# INITIALIZE
# --------------------------------------------------

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

create_tables()


# --------------------------------------------------
# GET JOB DESCRIPTION
# --------------------------------------------------

print("\nJOB AGENT")
print("---------")

job = collect_manual_job()

job_title = job["job_title"]
company = job["company"]
location = job["location"]
salary = job["salary"]
posted_date = job["posted_date"]
source = job["source"]
source_url = job["source_url"]
job_description = job["description"]

if not job_description:
    print("\nNo job description provided.")
    raise SystemExit(1)

if posted_date:
    within_30_days = is_within_30_days(posted_date)

    if within_30_days is False:
        print("\nJob is older than 30 days. Skipping Gemini analysis.")
        raise SystemExit(0)

    if within_30_days is None:
        print("\nWarning: Could not verify posted date. Continuing without date filter.")

duplicate_id = find_duplicate_job(job_title, company, location)
if duplicate_id:
    print(f"\nDuplicate job found. Existing Job ID: {duplicate_id}")
    print("Skipping Gemini analysis.")
    raise SystemExit(0)

# --------------------------------------------------
# AI MATCHING PROMPT
# --------------------------------------------------

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
- If evidence is insufficient, mark it as a gap.

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
- If the job description does not state a minimum experience requirement, do not claim that the candidate has no experience gap or that the candidate meets/exceeds an experience requirement.
- If the job description is brief or lacks sufficient evidence to assess a requirement, state that the requirement is not stated or cannot be assessed.
- Do not convert a general background in a field into direct professional experience in a specific function, industry, software or process.
- Do not treat education as evidence of professional work experience.
- Do not describe an academic degree as a stronger match than the actual responsibilities and skills required by the job.

MATCH CATEGORY:
Use exactly one:
- Strong Match
- Potential Match
- Low Relevance
- Strong Match requires substantial direct evidence across the job's core
  responsibilities and important requirements.
- Do not assign Strong Match solely because the job title belongs to a
  priority job family or because the candidate has a relevant degree.
- When evidence is limited because the job description is short or vague,
  prefer Potential Match rather than making unsupported assumptions.

LANGUAGE:
Follow the Matching Rules exactly.
Do not treat A1/A2 Dutch as fluent or professional Dutch.

SALARY:
Salary must never affect Match Category.

CANDIDATE MASTER PROFILE:
{yaml.dump(master_profile, allow_unicode=True, sort_keys=False)}

MATCHING RULES:
{yaml.dump(matching_rules, allow_unicode=True, sort_keys=False)}

JOB DESCRIPTION:
{job_description}

Return ONLY valid JSON.
Do not use Markdown.
Do not include ```json.
Do not add explanations outside the JSON.

IMPORTANT METADATA:
- job_title, company, location, and posted_date must use the values provided by the user.
- Do not infer, replace, or modify these metadata fields.

Use exactly this JSON structure:

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
- Do not create a gap for a tool, qualification or requirement unless the job
  description actually mentions it or clearly implies it as a responsibility.
- If a requirement is not mentioned in the job description, classify it as
  Not stated rather than Gap.
- Avoid phrases such as "fully satisfies", "meets or exceeds", "strong
  educational alignment", or "no experience gap" unless the job description
  provides sufficient explicit evidence to support that conclusion.
"""

interaction = client.interactions.create(
    model="gemini-3.6-flash",
    input=prompt,
)


# --------------------------------------------------
# PARSE AI RESPONSE
# --------------------------------------------------

raw_response = interaction.output_text.strip()

try:
    analysis = json.loads(raw_response)
except json.JSONDecodeError:
    print("\nERROR: Gemini did not return valid JSON.")
    print("\nRAW RESPONSE:\n")
    print(raw_response)
    raise SystemExit(1)


# --------------------------------------------------
# SAVE JOB TO DATABASE
# --------------------------------------------------

conn = get_connection()
cursor = conn.cursor()

cursor.execute("""
    INSERT INTO jobs (
        job_title,
        company,
        job_family,
        seniority,
        location,
        country,
        work_model,
        salary,
        salary_period,
        salary_type,
        posted_date,
        days_old,
        job_description,
        key_requirements,
        dutch_requirement,
        education_requirement,
        experience_requirement,
        match_category,
        why_match,
        gaps,
        priority,
        date_found
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
""", (
    job_title,
    company,
    analysis["job_family"],
    analysis["seniority"],
    location,
    analysis["country"],
    analysis["work_model"],
    analysis["salary"],
    analysis["salary_period"],
    analysis["salary_type"],
    posted_date,
    analysis["days_old"],
    job_description,
    json.dumps(analysis["key_requirements"], ensure_ascii=False),
    analysis["dutch_requirement"],
    analysis["education_requirement"],
    analysis["experience_requirement"],
    analysis["match_category"],
    json.dumps(analysis["why_match"], ensure_ascii=False),
    json.dumps(analysis["gaps"], ensure_ascii=False),
    analysis["priority"]
))


job_id = cursor.lastrowid
cursor.execute("""
    INSERT INTO job_sources (
        job_id,
        source,
        source_url,
        date_found,
        source_posted_date,
        is_primary
    )
    VALUES (?, ?, ?, datetime('now'), ?, ?)
""", (
    job_id,
    source,
    source_url,
    analysis["posted_date"],
    1
))

cursor.execute("""
    INSERT INTO job_matches (
        job_id,
        match_category,
        match_reason,
        direct_matches,
        transferable_matches,
        gaps,
        experience_gap,
        education_match,
        language_match,
        overall_notes
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    job_id,
    analysis["match_category"],
    json.dumps(analysis["why_match"], ensure_ascii=False),
    json.dumps(analysis["direct_matches"], ensure_ascii=False),
    json.dumps(analysis["transferable_matches"], ensure_ascii=False),
    json.dumps(analysis["gaps"], ensure_ascii=False),
    analysis["experience_gap"],
    analysis["education_match"],
    analysis["language_match"],
    ""
))

conn.commit()
conn.close()


# --------------------------------------------------
# DISPLAY RESULT
# --------------------------------------------------

print("\n===== JOB ANALYSIS =====\n")

print(f"Job ID: {job_id}")
print(f"Job Title: {job_title}")
print(f"Company: {company}")
print(f"Job Family: {analysis['job_family']}")
print(f"Match Category: {analysis['match_category']}")
print(f"Location: {location}")
print(f"Work Model: {analysis['work_model']}")
print(f"Salary: {salary}")
print("\nWhy Match:")
for item in analysis["why_match"]:
    print(f"- {item}")

print("\nDirect Matches:")
for item in analysis["direct_matches"]:
    print(f"- {item}")

print("\nTransferable Matches:")
for item in analysis["transferable_matches"]:
    print(f"- {item}")

print("\nGaps:")
for item in analysis["gaps"]:
    print(f"- {item}")

print("\nExperience Gap:")
print(analysis["experience_gap"])

print("\nEducation Match:")
print(analysis["education_match"])

print("\nLanguage Match:")
print(analysis["language_match"])

print("\nSaved to database successfully.")
