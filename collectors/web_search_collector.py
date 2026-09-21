import os

from tavily import TavilyClient

from collectors.search_provider import SearchProvider


JOB_SITE_DOMAINS = [
    "linkedin.com/jobs",
    "indeed.com",
    "indeed.nl",
    "nationalevacaturebank.nl",
    "intermediair.nl",
    "michaelpage.nl",
    "robertwalters.nl",
    "hays.nl",
    "yacht.nl",
    "randstad.nl",
    "adecco.nl",
]


EXCLUDED_DOMAINS = [
    "salaryexpert.com",
    "plane.com",
    "glassdoor.com",
    "remoterocketship.com",
    "startup.jobs",
    "builtin.com",
    "magnet.me",
]


EXCLUDED_URL_PATTERNS = [
    "/salary/",
    "/salaries/",
    "/locations/",
    "/search/",
    "/jobs/human-resources",
    "/jobs/order-management",
    "/jobs/business-continuity",
    "/jobs/jp-gray",
    "/en/jobs/international/",
    "/q-",
]


class WebSearchCollector(SearchProvider):

    name = "Tavily Web Search"

    def __init__(self):
        api_key = os.environ.get("TAVILY_API_KEY")

        if not api_key:
            raise RuntimeError(
                "TAVILY_API_KEY is not set."
            )

        self.client = TavilyClient(
            api_key=api_key
        )

    def build_query(self, job_title):

        site_filter = " OR ".join(
            f"site:{domain}"
            for domain in JOB_SITE_DOMAINS
        )

        return (
            f'"{job_title}" '
            f'Netherlands '
            f'({site_filter}) '
            f'-salary -salaries'
        )

    def is_job_url(self, url):

        url_lower = url.lower()

        for domain in EXCLUDED_DOMAINS:
            if domain in url_lower:
                return False

        for pattern in EXCLUDED_URL_PATTERNS:
            if pattern in url_lower:
                return False

        if "linkedin.com/jobs/view/" in url_lower:
            return True

        if "indeed.com/viewjob" in url_lower:
            return True

        if "indeed.nl/viewjob" in url_lower:
            return True

        if any(
            domain in url_lower
            for domain in [
                "nationalevacaturebank.nl",
                "intermediair.nl",
                "michaelpage.nl",
                "robertwalters.nl",
                "hays.nl",
                "yacht.nl",
                "randstad.nl",
                "adecco.nl",
            ]
        ):
            return True

        return False

    def search_jobs(
        self,
        job_title,
        max_results=20
    ):

        query = self.build_query(job_title)

        response = self.client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results
        )

        results = []

        for item in response.get("results", []):

            title = item.get("title", "")
            url = item.get("url", "")
            snippet = item.get("content", "")

            if not url:
                continue

            if not self.is_job_url(url):
                continue

            results.append({
                "title": title,
                "url": url,
                "snippet": snippet
            })

        return results


if __name__ == "__main__":

    collector = WebSearchCollector()

    results = collector.search_jobs(
        "Business Operations Specialist",
        max_results=20
    )

    print("\nFILTERED JOB RESULTS")
    print("--------------------")

    print(f"Jobs found: {len(results)}")

    for result in results:
        print()
        print(result["title"])
        print(result["url"])
