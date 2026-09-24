from datetime import date, timedelta
from hashlib import sha256
import os
import re

from collectors.indeed_collector import IndeedCollector
from collectors.web_search_collector import WebSearchCollector


def _normalize_url(url):
    return str(url or "").strip()


def _source_job_id(source, url):
    normalized = _normalize_url(url)

    if not normalized:
        return ""

    digest = sha256(normalized.encode("utf-8")).hexdigest()[:24]

    return f"{source}:{digest}"


def _parse_relative_date(text):
    """
    Parse common Dutch/English relative job-posting dates.

    Returns:
        YYYY-MM-DD string, or "" when the date cannot be determined.
    """
    value = str(text or "").strip().lower()

    if not value:
        return ""

    today = date.today()

    if any(term in value for term in (
        "vandaag",
        "today",
    )):
        return today.isoformat()

    if any(term in value for term in (
        "gisteren",
        "yesterday",
    )):
        return (today - timedelta(days=1)).isoformat()

    # Dutch:
    # "1 dag geleden"
    # "3 dagen geleden"
    # English:
    # "1 day ago"
    # "3 days ago"
    match = re.search(
        r"(\d+)\s*(?:dag|dagen|day|days)\s*(?:geleden|ago)",
        value,
    )

    if match:
        days = int(match.group(1))
        return (today - timedelta(days=days)).isoformat()

    # Weeks.
    match = re.search(
        r"(\d+)\s*(?:week|weken|week|weeks)\s*(?:geleden|ago)",
        value,
    )

    if match:
        weeks = int(match.group(1))
        return (today - timedelta(weeks=weeks)).isoformat()

    return ""


def _parse_absolute_date(text):
    """
    Parse common Dutch/English absolute dates.

    Returns YYYY-MM-DD or "".
    """
    value = str(text or "").strip()

    if not value:
        return ""

    # ISO date.
    match = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", value)

    if match:
        year, month, day = map(int, match.groups())

        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""

    # dd-mm-yyyy / dd/mm/yyyy
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
    """
    Resolve a posting date without inventing one.
    """
    return (
        _parse_absolute_date(text)
        or _parse_relative_date(text)
    )


def collect_indeed_discovery():
    collector = IndeedCollector()

    max_queries = int(
        os.environ.get(
            "JOB_DISCOVERY_MAX_QUERIES",
            "0",
        )
    )

    queries = collector.get_queries()

    if max_queries > 0:
        queries = queries[:max_queries]

    print()
    print("=" * 50)
    print("DISCOVERY: INDEED")
    print("=" * 50)
    print(f"Queries: {len(queries)}")

    jobs = []
    seen_urls = set()

    for item in queries:
        query = item["query"]

        print(f"Searching Indeed: {query}")

        try:
            found = collector.collect_search_page(
                query=query,
                location="Netherlands",
            )

            for job in found:
                data = job.to_dict()
                url = data["source_url"]

                if url and url in seen_urls:
                    continue

                if url:
                    seen_urls.add(url)

                jobs.append(job)

        except Exception as error:
            print(f"  Indeed error: {error}")

    print(f"Indeed discovery results: {len(jobs)}")

    return jobs


def collect_tavily_discovery():
    if not os.environ.get("TAVILY_API_KEY"):
        print()
        print("DISCOVERY: TAVILY")
        print("=" * 50)
        print("Skipped: TAVILY_API_KEY is not set.")
        return []

    collector = WebSearchCollector()

    max_queries = int(
        os.environ.get(
            "JOB_DISCOVERY_MAX_QUERIES",
            "0",
        )
    )

    queries = collector.get_queries()

    if max_queries > 0:
        queries = queries[:max_queries]

    print()
    print("=" * 50)
    print("DISCOVERY: TAVILY")
    print("=" * 50)
    print(f"Queries: {len(queries)}")

    jobs = []
    seen_urls = set()

    for item in queries:
        query = item["query"]

        print(f"Searching Tavily: {query}")

        try:
            results = collector.search_jobs(
                job_title=query,
                max_results=10,
            )

            for result in results:
                url = _normalize_url(result.get("url"))

                if not url or url in seen_urls:
                    continue

                seen_urls.add(url)

                jobs.append(
                    collector.result_to_job(result)
                )

        except Exception as error:
            print(f"  Tavily error: {error}")

    print(f"Tavily discovery results: {len(jobs)}")

    return jobs
