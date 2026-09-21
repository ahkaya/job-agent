from datetime import datetime

from collectors.location_resolver import classify_location
from collectors.keyword_config import (
    BLACKLIST_TITLES,
    ENGINEER_ALLOWED_PATTERNS,
    SENIORITY_EXCLUDE,
    MAX_JOB_AGE_DAYS,
)


REMOTE_EXCLUDE_TERMS = [
    "fully remote",
    "100% remote",
    "100% remotely",
    "work from anywhere",
    "work-from-anywhere",
    "remote-first",
    "fully distributed",
]


def normalize_text(text):
    return " ".join(
        str(text or "").lower().split()
    )


def is_within_job_age(posted_date):
    if not posted_date:
        return False

    try:
        posted = datetime.strptime(
            posted_date,
            "%Y-%m-%d"
        ).date()

        age = (
            datetime.now().date() - posted
        ).days

        return 0 <= age <= MAX_JOB_AGE_DAYS

    except ValueError:
        return False


def contains_any(text, keywords):
    normalized = normalize_text(text)

    return any(
        normalize_text(keyword) in normalized
        for keyword in keywords
    )


def is_blacklisted_title(job_title):
    return contains_any(
        job_title,
        BLACKLIST_TITLES
    )


def is_excluded_seniority(job_title):
    return contains_any(
        job_title,
        SENIORITY_EXCLUDE
    )


def is_excluded_engineer_role(job_title):
    """
    Exclude Engineer roles by default.

    Engineer roles are kept only when the title clearly indicates
    a business, operations, supply-chain, logistics, process,
    industrial, continuous-improvement, or manufacturing focus.
    """

    normalized_title = normalize_text(job_title)

    if "engineer" not in normalized_title:
        return False

    return not any(
        normalize_text(pattern) in normalized_title
        for pattern in ENGINEER_ALLOWED_PATTERNS
    )


def is_fully_remote(job):
    """
    Exclude jobs that are explicitly described as fully remote.

    We check the job title, location, and description because
    some ATS records may contain a physical city even when the
    role itself is remote.

    Hybrid roles are not excluded.
    """

    title = normalize_text(
        getattr(job, "job_title", "")
    )

    location = normalize_text(
        getattr(job, "location", "")
    )

    description = normalize_text(
        getattr(job, "description", "")
    )

    combined_text = " ".join([
        title,
        location,
        description,
    ])

    if any(
        term in combined_text
        for term in REMOTE_EXCLUDE_TERMS
    ):
        return True

    if title == "remote" or title.endswith(" remote"):
        return True

    if " remote " in title:
        return True

    if location == "remote":
        return True

    if location.startswith("remote "):
        return True

    if location.endswith(" remote"):
        return True

    if " remote - " in location:
        return True

    if " remote, " in location:
        return True

    return False


def filter_jobs(jobs):
    """
    Apply deterministic, high-confidence filters.

    Role relevance is intentionally NOT filtered here.
    Gemini will evaluate responsibilities, transferable
    experience, skills, and overall fit for the remaining jobs.
    """

    filtered_jobs = []

    statistics = {
        "input": len(jobs),
        "too_old": 0,
        "wrong_location": 0,
        "regional_ambiguous": 0,
        "unknown_location": 0,
        "blacklisted": 0,
        "excluded_seniority": 0,
        "excluded_engineer": 0,
        "excluded_remote": 0,
        "kept": 0,
    }

    for job in jobs:

        # 1. Job age
        if not is_within_job_age(job.posted_date):
            statistics["too_old"] += 1
            continue

        # 2. Location
        location_class = classify_location(
            job.location
        )

        if location_class == "NOT_NL":
            statistics["wrong_location"] += 1
            continue

        if location_class == "REGIONAL_AMBIGUOUS":
            statistics["regional_ambiguous"] += 1
            continue

        if location_class == "UNKNOWN":
            statistics["unknown_location"] += 1
            continue

        # 3. Fully remote jobs
        if is_fully_remote(job):
            statistics["excluded_remote"] += 1
            continue

        # 4. Blacklisted job titles
        if is_blacklisted_title(job.job_title):
            statistics["blacklisted"] += 1
            continue

        # 5. Clearly excluded seniority
        if is_excluded_seniority(job.job_title):
            statistics["excluded_seniority"] += 1
            continue

        # 6. Engineer roles
        if is_excluded_engineer_role(job.job_title):
            statistics["excluded_engineer"] += 1
            continue

        # 7. No general role-relevance filter here.
        # Gemini evaluates the remaining jobs.
        filtered_jobs.append(job)

    statistics["kept"] = len(filtered_jobs)

    return filtered_jobs, statistics


if __name__ == "__main__":
    print("JOB FILTER READY")
