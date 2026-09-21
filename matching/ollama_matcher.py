import json

from ollama import chat

from matching.gemini_matcher import (
    load_matching_config,
)


MODEL_NAME = "qwen3.5:9b"


MATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "match_category": {
            "type": "string",
            "enum": [
                "Strong Match",
                "Potential Match",
                "Low Relevance",
            ],
        },
        "job_family": {
            "type": "string",
        },
        "seniority": {
            "type": "string",
        },
        "direct_matches": {
            "type": "array",
            "items": {
                "type": "string",
            },
        },
        "transferable_matches": {
            "type": "array",
            "items": {
                "type": "string",
            },
        },
        "gaps": {
            "type": "array",
            "items": {
                "type": "string",
            },
        },
        "experience_gap": {
            "type": "string",
        },
        "education_match": {
            "type": "string",
        },
        "language_match": {
            "type": "string",
        },
    },
    "required": [
        "match_category",
        "job_family",
        "seniority",
        "direct_matches",
        "transferable_matches",
        "gaps",
        "experience_gap",
        "education_match",
        "language_match",
    ],
}


def build_local_prompt(job, master_profile, matching_rules):

    description = (
        job.get("job_description", "")
        or job.get("description", "")
    )

    profile = json.dumps(
        master_profile,
        ensure_ascii=False,
        indent=2,
    )

    rules = json.dumps(
        matching_rules,
        ensure_ascii=False,
        indent=2,
    )

    return f"""
You are a strict job-matching analyst.

Compare ONE job with the candidate's verified Master Profile.

The Master Profile is the ONLY evidence about the candidate.

Never invent experience, skills, tools, responsibilities,
achievements, metrics, dates, education or certifications.

If something is not explicitly supported by the Master Profile,
it is NOT a match.

Academic/research experience must remain academic/research
experience. Do not convert it into industry experience.

MATCH CATEGORIES:

Strong Match:
Substantial direct evidence for the core responsibilities
and important requirements.

Potential Match:
Relevant transferable evidence exists, but important gaps remain.

Low Relevance:
Limited relevant overlap.

Do not give Strong Match simply because the job title sounds similar.

Do not treat a degree as professional work experience.

For direct_matches:
include only clearly verified direct evidence.

For transferable_matches:
include only credible transferable evidence.

For gaps:
include important requirements that are not supported
by the Master Profile.

Do not repeat the same evidence in multiple categories.

Do not invent missing information.

JOB TITLE:
{job.get("job_title", "")}

COMPANY:
{job.get("company", "")}

LOCATION:
{job.get("location", "")}

JOB DESCRIPTION:
{description}

MASTER PROFILE:
{profile}

MATCHING RULES:
{rules}

Return ONLY the requested JSON.
"""


def analyze_job_local(job):

    master_profile, matching_rules = (
        load_matching_config()
    )

    prompt = build_local_prompt(
        job,
        master_profile,
        matching_rules,
    )

    response = chat(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        format=MATCH_SCHEMA,
        options={
            "temperature": 0,
        },
        think=False,
    )

    raw_response = (
        response.message.content.strip()
    )

    try:
        analysis = json.loads(
            raw_response
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            "Ollama did not return valid JSON."
        ) from error

    return analysis