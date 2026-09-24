from datetime import datetime

import requests

from collectors.base_collector import BaseCollector
from collectors.job_schema import Job


class SmartRecruitersCollector(BaseCollector):

    source_name = "SmartRecruiters"

    BASE_URL = (
        "https://api.smartrecruiters.com/"
        "v1/companies"
    )

    PAGE_SIZE = 100

    def build_url(self, company_identifier):
        return (
            f"{self.BASE_URL}/"
            f"{company_identifier}/postings"
        )

    def parse_date(self, value):
        if not value:
            return ""

        value = str(value).strip()

        try:
            parsed = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
            return parsed.date().isoformat()

        except ValueError:
            return ""

    def fetch_job_details(self, company_identifier, posting_id):
        url = f"{self.BASE_URL}/{company_identifier}/postings/{posting_id}"
        response = requests.get(
            url,
            headers={"User-Agent": "job-agent/1.0"},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def extract_job_content(self, data):
        job_ad = data.get("jobAd", {}) or {}
        sections = job_ad.get("sections", {}) or {}

        if isinstance(sections, list):
            section_items = {}
            for section in sections:
                if isinstance(section, dict):
                    title = str(section.get("title", "")).strip().lower()
                    text = str(section.get("text", "")).strip()
                    if title and text:
                        section_items[title] = text
            sections = section_items

        description_parts = []
        qualification_parts = []

        for key, value in sections.items():
            if isinstance(value, dict):
                text = str(value.get("text", "")).strip()
            else:
                text = str(value or "").strip()

            if not text:
                continue

            key_normalized = str(key).lower()
            if "qualif" in key_normalized or "require" in key_normalized:
                qualification_parts.append(text)
            else:
                description_parts.append(text)

        return "\n\n".join(description_parts), "\n\n".join(qualification_parts)

    def collect_company(
        self,
        board_token,
        company_name=None,
    ):
        base_url = self.build_url(board_token)

        jobs = []
        offset = 0
        total_found = None

        while True:

            response = requests.get(
                base_url,
                params={
                    "limit": self.PAGE_SIZE,
                    "offset": offset,
                },
                headers={
                    "User-Agent": "job-agent/1.0"
                },
                timeout=20,
            )

            response.raise_for_status()

            data = response.json()

            content = data.get(
                "content",
                []
            )

            if total_found is None:
                total_found = data.get(
                    "totalFound"
                )

            if not content:
                break

            for item in content:

                location_data = item.get(
                    "location",
                    {}
                )

                if isinstance(
                    location_data,
                    dict
                ):
                    city = location_data.get(
                        "city",
                        ""
                    )
                    region = location_data.get(
                        "region",
                        ""
                    )
                    country = location_data.get(
                        "country",
                        ""
                    )

                    location_parts = [
                        value
                        for value in (
                            city,
                            region,
                            country,
                        )
                        if value
                    ]

                    location = ", ".join(
                        location_parts
                    )

                else:
                    location = str(
                        location_data or ""
                    )

                posted_date = self.parse_date(
                    item.get("releasedDate")
                )

                job_url = str(
                    item.get("ref", "")
                ).strip()

                if not job_url:
                    job_id = str(
                        item.get("id", "")
                    ).strip()

                    if job_id:
                        job_url = (
                            f"{base_url}/{job_id}"
                        )

                posting_id = str(
                    item.get(
                        "id",
                        ""
                    )
                ).strip()

                description = ""
                key_requirements = ""

                if posting_id:
                    try:
                        detail_data = self.fetch_job_details(
                            board_token,
                            posting_id,
                        )
                        (
                            description,
                            key_requirements,
                        ) = self.extract_job_content(
                            detail_data
                        )
                    except (
                        requests.RequestException,
                        ValueError,
                    ):
                        pass

                job = Job(
                    job_title=item.get(
                        "name",
                        ""
                    ),
                    company=(
                        company_name
                        if company_name
                        else board_token
                    ),
                    location=location,
                    posted_date=posted_date,
                    source=self.source_name,
                    source_url=job_url,
                    description=(
                        description
                        + (
                            "\n\nREQUIREMENTS:\n"
                            + key_requirements
                            if key_requirements
                            else ""
                        )
                    ),
                    source_job_id=posting_id,
                )

                jobs.append(job)

            offset += len(content)

            if (
                total_found is not None
                and offset >= total_found
            ):
                break

            if len(content) < self.PAGE_SIZE:
                break

        return jobs
