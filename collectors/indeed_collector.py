import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

from collectors.base_collector import BaseCollector


class IndeedCollector(BaseCollector):

    source_name = "Indeed Netherlands"

    BASE_URL = "https://nl.indeed.com/jobs"

    def build_search_url(self, query, location="Netherlands"):
        return (
            f"{self.BASE_URL}"
            f"?q={quote(query)}"
            f"&l={quote(location)}"
        )

    def collect_search_page(self, query, location="Netherlands"):
        url = self.build_search_url(query, location)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/150.0.0.0 Safari/537.36"
            )
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        jobs = []

        for card in soup.select("div.job_seen_beacon"):

            title_element = card.select_one(
                "h2.jobTitle"
            )

            company_element = card.select_one(
                "[data-testid='company-name']"
            )

            location_element = card.select_one(
                "[data-testid='text-location']"
            )

            link_element = card.select_one(
                "h2.jobTitle a"
            )

            if not title_element:
                continue

            title = title_element.get_text(
                " ",
                strip=True
            )

            company = (
                company_element.get_text(
                    " ",
                    strip=True
                )
                if company_element
                else ""
            )

            location_text = (
                location_element.get_text(
                    " ",
                    strip=True
                )
                if location_element
                else ""
            )

            job_url = ""

            if link_element:
                href = link_element.get("href", "")

                if href.startswith("/"):
                    job_url = (
                        "https://nl.indeed.com"
                        + href
                    )
                else:
                    job_url = href

            jobs.append(
                self.normalize_job(
                    {
                        "job_title": title,
                        "company": company,
                        "location": location_text,
                        "source_url": job_url,
                        "description": "",
                    }
                )
            )

        return jobs

    def collect(self):
        from collectors.search_queries import build_search_queries

        all_jobs = []
        seen_urls = set()

        queries = build_search_queries()

        for item in queries:
            query = item["query"]

            print(f"Searching: {query}")

            try:
                jobs = self.collect_search_page(
                    query=query,
                    location="Netherlands"
                )

                for job in jobs:
                    job_url = job.to_dict()["source_url"]

                    if job_url and job_url in seen_urls:
                        continue

                    if job_url:
                        seen_urls.add(job_url)

                    all_jobs.append(job)

            except Exception as e:
                print(f"  Error: {e}")

        return all_jobs
