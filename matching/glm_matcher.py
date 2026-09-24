from dotenv import load_dotenv
load_dotenv()

import json
import os

from openai import OpenAI

from matching.gemini_matcher import (
    load_matching_config,
    build_matching_prompt,
)


MODEL_NAME = "glm-5.3-flash"
BASE_URL = "https://api.z.ai/api/paas/v4/"


GLM_OUTPUT_DISCIPLINE = """
GLM OUTPUT DISCIPLINE — STRICT:

The JSON structure defined above remains mandatory.

Keep the output concise and evidence-based.

LIST LIMITS:
- why_match: maximum 3 items.
- direct_matches: maximum 3 items.
- transferable_matches: maximum 4 items.
- gaps: maximum 6 items.
- key_requirements: maximum 8 items.

RELEVANCE:
- Every list item must be directly relevant to the job's stated
  requirements or core responsibilities.
- Do not include generic soft skills, generic communication,
  generic independence, generic international exposure, or
  unrelated training as transferable matches.
- Prefer fewer strong items over many weak items.

TRANSFERABLE MATCH THRESHOLD:
- Include a transferable match only when the candidate's evidence
  provides a meaningful functional bridge to a specific responsibility
  or requirement in the job.
- Do not include transferable matches merely because they demonstrate
  generic execution, communication, coordination, training, exposure,
  or independence.
- If the connection would require more than one reasonable inference,
  omit it.
- When in doubt, omit the item rather than include a weak transferable
  match.

DIRECT MATCH RULE:
- "direct_matches" means the candidate's verified evidence directly
  satisfies a requirement or responsibility stated in the job.
- Do not classify location, work authorization, language compatibility,
  or absence of a Dutch requirement as a direct match unless the job
  explicitly lists that item as a requirement.
- Do not treat general education as a direct match for a specific
  professional skill unless the job requirement is educational.
- Do not turn academic experience into professional industry experience.

GAP RULE:
- Only list a gap when the job description explicitly requires or
  clearly implies the missing skill, experience, qualification, tool,
  responsibility, or knowledge.
- Do not create gaps from generic differences between the profile and
  the job.
- Do not repeat the same gap in multiple forms.

NO REPETITION:
- Do not repeat the same evidence across why_match,
  direct_matches, transferable_matches, and gaps unless necessary
  for a genuinely different purpose.
- Avoid restating the job description.

PRIORITY:
- priority MUST be exactly one of:
  High
  Medium
  Normal
  Low
- Do not add explanations, parentheses, rankings, or extra text
  to the priority value.

CONCISENESS:
- Prefer one concise sentence per list item.
- Do not enumerate every related detail from the Master Profile.
- Do not produce long narrative explanations.
- Use the minimum amount of text needed to support the classification.

MATCH CATEGORY:
- Keep the same three allowed values:
  Strong Match
  Potential Match
  Low Relevance
- Do not upgrade a match merely because several transferable items
  exist.
- Strong Match still requires substantial direct evidence across
  the job's core responsibilities and important requirements.

Return ONLY valid JSON.
"""


REQUIRED_KEYS = {
    "job_title",
    "company",
    "job_family",
    "seniority",
    "location",
    "country",
    "work_model",
    "salary",
    "salary_period",
    "salary_type",
    "posted_date",
    "days_old",
    "key_requirements",
    "dutch_requirement",
    "education_requirement",
    "experience_requirement",
    "match_category",
    "why_match",
    "direct_matches",
    "transferable_matches",
    "gaps",
    "experience_gap",
    "education_match",
    "language_match",
    "priority",
}


def _validate_analysis(analysis):
    if not isinstance(analysis, dict):
        raise ValueError("GLM response must be a JSON object.")

    missing_keys = REQUIRED_KEYS - set(analysis)
    if missing_keys:
        raise ValueError(
            "GLM response is missing required keys: "
            + ", ".join(sorted(missing_keys))
        )

    allowed_match_categories = {
        "Strong Match",
        "Potential Match",
        "Low Relevance",
    }

    if analysis["match_category"] not in allowed_match_categories:
        raise ValueError(
            "Invalid match_category: "
            + repr(analysis["match_category"])
        )

    allowed_priorities = {
        "High",
        "Medium",
        "Normal",
        "Low",
    }

    if analysis["priority"] not in allowed_priorities:
        raise ValueError(
            "Invalid priority: "
            + repr(analysis["priority"])
        )

    list_fields = [
        "key_requirements",
        "why_match",
        "direct_matches",
        "transferable_matches",
        "gaps",
    ]

    for field in list_fields:
        if not isinstance(analysis[field], list):
            raise ValueError(
                f"GLM field '{field}' must be a list."
            )

    limits = {
        "key_requirements": 8,
        "why_match": 3,
        "direct_matches": 3,
        "transferable_matches": 4,
        "gaps": 6,
    }

    for field, maximum in limits.items():
        if len(analysis[field]) > maximum:
            raise ValueError(
                f"GLM field '{field}' exceeds maximum length "
                f"of {maximum}."
            )

    if analysis["country"] != "Netherlands":
        raise ValueError(
            "GLM returned unexpected country value: "
            + repr(analysis["country"])
        )

    return analysis


def analyze_job(job):
    if not os.environ.get("GLM_API_KEY"):
        raise RuntimeError("GLM_API_KEY is not set.")

    master_profile, matching_rules = load_matching_config()

    prompt = build_matching_prompt(
        job,
        master_profile,
        matching_rules,
    )

    prompt += GLM_OUTPUT_DISCIPLINE

    client = OpenAI(
        api_key=os.environ["GLM_API_KEY"],
        base_url=BASE_URL,
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=0,
    )

    raw_response = (
        response.choices[0].message.content or ""
    ).strip()

    if not raw_response:
        raise ValueError("GLM returned an empty response.")

    try:
        analysis = json.loads(raw_response)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"GLM returned invalid JSON: {error}"
        ) from error

    _validate_analysis(analysis)

    return analysis
