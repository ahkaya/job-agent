import json

import requests
from bs4 import BeautifulSoup

from collectors.agencies.base import BaseAgencyCollector
from collectors.job_schema import Job


class AdeccoCollector(BaseAgencyCollector):
    source_name = "Adecco"
    base_url = "https://www.adecco.com"
    list_api = "https://www.adecco.com/api/data/jobs/summarized"
    detail_api_base = "https://www.adecco.com/api/data/jobs/job-description-details"

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
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://www.adecco.com",
            "Referer": "https://www.adecco.com/nl-nl/vacatures",
        })

    def _fetch_listing(self, range_offset=0):
        body = {
            "queryString": "&sort=PostedDate desc",
            "range": range_offset,
            "siteName": "adecco",
            "brand": "adecco",
            "countryCode": "NL",
            "languageCode": "nl-NL",
        }
        response = self.session.post(
            self.list_api,
            data=json.dumps(body),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def _fetch_detail(self, job_id):
        url = (
            f"{self.detail_api_base}/"
            f"{job_id}/adecco/NL/nl-NL/job-details"
        )
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, json.JSONDecodeError) as error:
            print(f"  Adecco detail error: {job_id} -> {error}")
            return {}

    def _detail_url(self, job_id):
        return f"{self.base_url}/nl-nl/vacature/{job_id.lower()}"

    def _build_salary(self, item):
        min_v = item.get("minsalary")
        max_v = item.get("maxsalary")
        symbol = item.get("salaryCurrencySymbol") or "EUR"
        timescale = item.get("salaryTimeScale") or ""

        if min_v is None and max_v is None:
            return ""

        def fmt(v):
            try:
                f = float(v)
                return str(int(f)) if f.is_integer() else f"{f:.2f}"
            except (TypeError, ValueError):
                return str(v)

        if min_v and max_v and min_v != max_v:
            salary = f"{fmt(min_v)} - {fmt(max_v)} {symbol}"
        elif min_v:
            salary = f"{fmt(min_v)} {symbol}"
        else:
            salary = f"{fmt(max_v)} {symbol}"

        if timescale:
            salary += f" per {timescale.lower()}"
        return salary

    def collect(self, max_pages=3):
        jobs = []
        seen_ids = set()
        range_offset = 0
        page = 0

        while page < max_pages:
            page += 1
            print(f"  Adecco page {page} (range={range_offset})")

            try:
                data = self._fetch_listing(range_offset)
            except (requests.RequestException, json.JSONDecodeError) as error:
                print(f"  Adecco list error: {error}")
                break

            listing = data.get("jobs", [])
            if not listing:
                print("  No jobs in listing; stopping.")
                break

            page_new = 0

            for item in listing:
                job_id = str(item.get("jobId", "")).strip()
                if not job_id or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                # Detay API'sinden description al
                detail = self._fetch_detail(job_id)

                title = self.clean_text(
                    detail.get("jobName")
                    or item.get("jobTitle")
                    or ""
                )
                if not title:
                    continue

                raw_desc = (
                    detail.get("jobDescription")
                    or detail.get("clientDescription")
                    or ""
                )
                description = self.clean_text(
                    BeautifulSoup(str(raw_desc), "html.parser").get_text(" ", strip=True)
                )

                # Location: detay > liste
                location = self.clean_text(
                    detail.get("location")
                    or item.get("jobLocation")
                    or item.get("cityName")
                    or ""
                )

                # Salary: detay > liste
                salary = self._build_salary(detail) or self._build_salary(item)

                # postedDate
                posted = (
                    detail.get("postedDate")
                    or item.get("postedDate")
                    or item.get("jobCreationDate")
                    or ""
                )
                posted_date = self.resolve_posted_date(str(posted)[:10])

                job = Job(
                    job_title=title,
                    company=self.clean_text(
                        detail.get("companyName") or "Adecco"
                    ),
                    location=location,
                    salary=salary,
                    posted_date=posted_date,
                    source=self.source_name,
                    source_url=self._detail_url(job_id),
                    description=description,
                    source_job_id=f"{self.source_name}:{job_id}",
                )
                jobs.append(job)
                page_new += 1

            print(f"  New jobs: {page_new}")

            if page_new == 0:
                break

            pagination = data.get("pagination", {})
            next_range = pagination.get("nextRange")
            if next_range is None or next_range == range_offset:
                break
            range_offset = next_range

        print(f"Adecco total collected: {len(jobs)}")
        return jobs
