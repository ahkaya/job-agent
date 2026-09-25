import json
import requests
from bs4 import BeautifulSoup

from collectors.agencies.base import BaseAgencyCollector
from collectors.job_schema import Job


class TempoTeamCollector(BaseAgencyCollector):
    source_name = "Tempo-Team"
    base_url = "https://www.tempo-team.nl"
    list_api = "https://www.tempo-team.nl/vacatures"

    def __init__(self, timeout=20):
        super().__init__(timeout=timeout)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Referer": "https://www.tempo-team.nl/vacatures",
        })

    def _fetch_listing(self, page):
        params = {
            "_hn:type": "resource",
            "_hn:ref": "r281_r1_r1",
            "pagina": page,
        }
        response = self.session.get(
            self.list_api,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def _detail_url(self, aanvraag_nummer):
        return f"{self.base_url}/vacatures/{aanvraag_nummer}"

    def _parse_detail(self, url):
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as error:
            print(f"  Tempo-Team detail error: {url} -> {error}")
            return {}

        soup = BeautifulSoup(response.text, "html.parser")
        return self.parse_json_ld_jobposting(soup)

    def collect(self, max_pages=3):
        jobs = []
        seen_ids = set()

        for page in range(1, max_pages + 1):
            print(f"  Tempo-Team page {page}")

            try:
                data = self._fetch_listing(page)
            except (requests.RequestException, json.JSONDecodeError) as error:
                print(f"  Tempo-Team list error: {error}")
                break

            listing = (
                data.get("relay42", {})
                .get("jobListing", [])
            )

            if not listing:
                print("  No jobs in listing; stopping.")
                break

            page_new = 0

            for item in listing:
                aanvraag = str(item.get("aanvraagNummer", "")).strip()
                if not aanvraag or aanvraag in seen_ids:
                    continue
                seen_ids.add(aanvraag)

                url = self._detail_url(aanvraag)
                fallback_title = self.clean_text(item.get("jobNaam", ""))
                fallback_location = self.clean_text(item.get("jobPlaats", ""))

                detail = self._parse_detail(url)

                title = detail.get("title") or fallback_title
                if not title:
                    continue

                job = Job(
                    job_title=title,
                    company=detail.get("company", "") or self.clean_text(item.get("BedrijfsNaam", "")),
                    location=detail.get("location", "") or fallback_location,
                    salary=detail.get("salary", ""),
                    posted_date=detail.get("posted_date", ""),
                    source=self.source_name,
                    source_url=url,
                    description=detail.get("description", ""),
                    source_job_id=(
                        f"{self.source_name}:{detail['identifier']}"
                        if detail.get("identifier")
                        else f"{self.source_name}:{aanvraag}"
                    ),
                )
                jobs.append(job)
                page_new += 1

            print(f"  New jobs: {page_new}")

            # Last page check
            total_pages = data.get("pages", 0)
            if page >= total_pages:
                break

        print(f"Tempo-Team total collected: {len(jobs)}")
        return jobs
