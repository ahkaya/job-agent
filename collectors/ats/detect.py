import re
import requests
from urllib.parse import urlparse


ATS_TIMEOUT = 10


def normalize_company_candidates(url):
    parsed = urlparse(url)

    hostname = parsed.netloc.lower()

    if hostname.startswith("www."):
        hostname = hostname[4:]

    domain_parts = hostname.split(".")

    if not domain_parts:
        return []

    candidates = []

    # Primary domain label
    primary = domain_parts[0]

    if primary:
        candidates.append(primary)

    # Common company suffixes that should not become part
    # of the ATS board token.
    suffixes = {
        "hq",
        "inc",
        "corp",
        "corporation",
        "company",
        "co",
        "labs",
        "lab",
        "group",
        "holdings",
        "technologies",
        "technology",
    }

    cleaned = re.sub(
        r"[^a-z0-9-]",
        "",
        primary
    )

    if cleaned:
        candidates.append(cleaned)

        parts = cleaned.split("-")

        if parts and parts[-1] in suffixes:
            shortened = "-".join(parts[:-1])

            if shortened:
                candidates.append(shortened)

    # Remove duplicates while preserving order
    result = []

    for candidate in candidates:

        if candidate and candidate not in result:
            result.append(candidate)

    return result


def probe_greenhouse(board_token):
    url = (
        "https://boards-api.greenhouse.io/"
        f"v1/boards/{board_token}/jobs"
    )

    try:

        response = requests.get(
            url,
            params={"content": "false"},
            timeout=ATS_TIMEOUT,
        )

        if response.status_code != 200:
            return None

        data = response.json()

        if "jobs" not in data:
            return None

        return {
            "ats": "greenhouse",
            "board_token": board_token,
            "job_count": len(data["jobs"]),
        }

    except (
        requests.RequestException,
        ValueError,
    ):
        return None


def detect_greenhouse_from_company_url(url):

    candidates = normalize_company_candidates(url)

    for candidate in candidates:

        result = probe_greenhouse(candidate)

        if result:
            return result

    return None


def detect_ats(url):

    # First: direct ATS URL detection.
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if "greenhouse.io" in host:

        parts = [
            part
            for part in parsed.path.split("/")
            if part
        ]

        if parts:

            return {
                "ats": "greenhouse",
                "board_token": parts[0],
            }

    if "lever.co" in host:

        return {
            "ats": "lever",
            "board_token": None,
        }

    if "ashbyhq.com" in host:

        return {
            "ats": "ashby",
            "board_token": None,
        }

    if "smartrecruiters.com" in host:

        return {
            "ats": "smartrecruiters",
            "board_token": None,
        }

    # Second: probe likely Greenhouse board token.
    greenhouse = detect_greenhouse_from_company_url(url)

    if greenhouse:
        return greenhouse

    return None


if __name__ == "__main__":

    test_urls = [
        "https://stripe.com/nl/careers",
        "https://boards.greenhouse.io/stripe",
        "https://job-boards.greenhouse.io/stripe",
    ]

    for url in test_urls:

        print()
        print("URL:", url)

        result = detect_ats(url)

        print("RESULT:", result)
