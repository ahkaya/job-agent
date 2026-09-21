from datetime import datetime

import requests

from collectors.job_schema import Job
from collectors.base_collector import BaseCollector


class AshbyCollector(BaseCollector):

    source_name = "Ashby"
    BASE_URL = (
        "https://api.ashbyhq.com/"
        "posting-api/job-board"
    )

    def build_url(self, board_token):
        return (
            f"{self.BASE_URL}/"
            f"{board_token}"
            "?includeCompensation=true"
        )

    def parse_date(self, value):
        if not value:
            return ""

        try:
            parsed = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )

            return parsed.date().isoformat()

        except ValueError:
            return ""

    def collect_company(
        self,
        board_token,
        company_name=None,
    ):
        url = self.build_url(board_token)

        response = requests.get(
            url,
            headers={
                "User-Agent": "job-agent/1.0"
            },
            timeout=20,
        )

        response.raise_for_status()

        data = response.json()

        jobs = []

        for item in data.get("jobs", []):

            location = item.get(
                "location",
                ""
            )

            secondary_locations = item.get(
                "secondaryLocations",
                []
            )

            if secondary_locations:

                extra_locations = []

                for secondary in secondary_locations:

                    if isinstance(
                        secondary,
                        dict
                    ):
                        name = secondary.get(
                            "location",
                            ""
                        )

                        if name:
                            extra_locations.append(
                                name
                            )

                if extra_locations:

                    location = (
                        f"{location}; "
                        f"{'; '.join(extra_locations)}"
                    )

            salary = ""

            compensation = item.get(
                "compensation"
            )

            if compensation:

                if isinstance(
                    compensation,
                    str
                ):
                    salary = compensation

                elif isinstance(
                    compensation,
                    dict
                ):

                    summary = compensation.get(
                        "summary",
                        ""
                    )

                    if summary:
                        salary = summary

            description = item.get(
                "descriptionPlain",
                ""
            )

            if not description:

                description = item.get(
                    "descriptionHtml",
                    ""
                )

            posted_date = self.parse_date(
                item.get("publishedAt")
            )

            job = Job(
                job_title=item.get(
                    "title",
                    ""
                ),
                company=(
                    company_name
                    if company_name
                    else board_token
                ),
                location=location,
                salary=salary,
                posted_date=posted_date,
                source=self.source_name,
                source_url=item.get(
                    "jobUrl",
                    ""
                ),
                description=description,
                source_job_id=str(
                    item.get(
                        "id",
                        ""
                    )
                ),
            )

            jobs.append(job)

        return jobs