from datetime import date, timedelta
from hashlib import sha256
import re


def normalize_url(url):
    return str(url or "").strip()


def source_job_id(source, url):
    normalized = normalize_url(url)

    if not normalized:
        return ""

    digest = sha256(
        normalized.encode("utf-8")
    ).hexdigest()[:24]

    return f"{source}:{digest}"


def parse_relative_date(text):
    value = str(text or "").strip().lower()

    if not value:
        return ""

    today = date.today()

    if any(term in value for term in ("vandaag", "today")):
        return today.isoformat()

    if any(term in value for term in ("gisteren", "yesterday")):
        return (today - timedelta(days=1)).isoformat()

    match = re.search(
        r"(\d+)\s*(?:dag|dagen|day|days)\s*(?:geleden|ago)",
        value,
    )

    if match:
        return (
            today - timedelta(
                days=int(match.group(1))
            )
        ).isoformat()

    match = re.search(
        r"(\d+)\s*(?:week|weken|weeks)\s*(?:geleden|ago)",
        value,
    )

    if match:
        return (
            today - timedelta(
                weeks=int(match.group(1))
            )
        ).isoformat()

    return ""


def parse_absolute_date(text):
    value = str(text or "").strip()

    if not value:
        return ""

    match = re.search(
        r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b",
        value,
    )

    if match:
        year, month, day = map(int, match.groups())

        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""

    match = re.search(
        r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b",
        value,
    )

    if match:
        day, month, year = map(int, match.groups())

        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""

    return ""


def resolve_posted_date(text):
    return (
        parse_absolute_date(text)
        or parse_relative_date(text)
    )


def extract_jobposting_from_soup(soup):
    import json as _json

    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = _json.loads(script.get_text())
        except (_json.JSONDecodeError, TypeError):
            continue

        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item

    return None


def parse_json_ld_jobposting(soup, fallback_company=""):
    from bs4 import BeautifulSoup as _BS

    posting = extract_jobposting_from_soup(soup)

    if not posting:
        return {}

    def _clean(value):
        return " ".join(str(value or "").split()).strip()

    title = _clean(posting.get("title", ""))
    posted_date = resolve_posted_date(posting.get("datePosted", ""))

    location = ""
    job_location = posting.get("jobLocation", {})
    if isinstance(job_location, dict):
        address = job_location.get("address", {})
        if isinstance(address, dict):
            location = (
                address.get("addressLocality")
                or address.get("addressRegion")
                or ""
            )

    salary = ""
    base_salary = posting.get("baseSalary", {})
    if isinstance(base_salary, dict):
        value = base_salary.get("value", {})
        if isinstance(value, dict):
            min_v = value.get("minValue") or value.get("value") or ""
            max_v = value.get("maxValue") or ""
            unit_text = value.get("unitText", "")
            currency = base_salary.get("currency") or posting.get("salaryCurrency") or "EUR"

            if min_v and max_v:
                salary = f"{min_v} - {max_v} {currency}"
            elif min_v:
                salary = f"{min_v} {currency}"

            if salary and unit_text:
                salary += f" per {str(unit_text).lower()}"

    description = posting.get("description", "")
    description = _clean(
        _BS(str(description), "html.parser").get_text(" ", strip=True)
    )

    company = _clean(fallback_company)

    if not company:
        hiring = posting.get("hiringOrganization", {})
        if isinstance(hiring, dict):
            company = _clean(hiring.get("name", ""))
        elif isinstance(hiring, str):
            company = _clean(hiring)

    identifier = ""
    ident = posting.get("identifier")
    if isinstance(ident, dict):
        identifier = _clean(ident.get("value", ""))

    return {
        "title": title,
        "company": company,
        "location": _clean(location),
        "salary": _clean(salary),
        "posted_date": posted_date,
        "description": description,
        "identifier": identifier,
    }
