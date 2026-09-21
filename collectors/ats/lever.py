from datetime import datetime

import requests

from collectors.job_schema import Job
from collectors.base_collector import BaseCollector


class LeverCollector(BaseCollector):

    source_name = "Lever"
    BASE_URL = "https://api.lever.co/v0/postings"

    def build_url(self, board_token):
        return (
            f"{self.BASE_URL}/"
            f"{board_token}?mode=json"
        )

    def parse_created_at(self, created_at):
        if not created_at:
            return ""

        try:
            return (
                datetime.fromtimestamp(
                    created_at / 1000
                )
                .date()
                .isoformat()
            )

        except (
            TypeError,
            ValueError,
            OSError,
        ):
            return ""

    def clean_html(self, text):
        if not text:
            return ""

        import html
        import re

        text = html.unescape(text)

        text = re.sub(
            r"<br\s*/?>",
            "\n",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"</p\s*>",
            "\n",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"<[^>]+>",
            " ",
            text,
        )

        text = re.sub(
            r"[ \t]+",
            " ",
            text,
        )

        text = re.sub(
            r"\n\s*\n+",
            "\n\n",
            text,
        )

        return text.strip()

    def extract_description(self, item):
        description = item.get(
            "descriptionPlain",
            "",
        )

        if description:
            return description.strip()

        description_body = item.get(
            "descriptionBodyPlain",
            "",
        )

        if description_body:
            return description_body.strip()

        sections = []

        opening = item.get(
            "openingPlain",
            "",
        )

        if opening:
            sections.append(
                opening.strip()
            )

        lists = item.get(
            "lists",
            [],
        )

        for section in lists:

            if not isinstance(
                section,
                dict,
            ):
                continue

            section_title = section.get(
                "text",
                "",
            )

            content = section.get(
                "content",
                "",
            )

            if section_title:
                sections.append(
                    section_title.strip()
                )

            if content:
                cleaned_content = (
                    self.clean_html(content)
                )

                if cleaned_content:
                    sections.append(
                        cleaned_content
                    )

        additional_plain = item.get(
            "additionalPlain",
            "",
        )

        if additional_plain:
            sections.append(
                additional_plain.strip()
            )

        return "\n\n".join(
            section
            for section in sections
            if section
        ).strip()

    def collect_company(
        self,
        board_token,
        company_name=None,
    ):
        url = self.build_url(
            board_token
        )

        response = requests.get(
            url,
            headers={
                "User-Agent": "job-agent/1.0",
                "Accept": "application/json",
            },
            timeout=20,
        )

        response.raise_for_status()

        data = response.json()

        jobs = []

        for item in data:

            categories = item.get(
                "categories",
                {},
            )

            location = categories.get(
                "location",
                "",
            )

            salary = ""

            salary_range = item.get(
                "salaryRange"
            )

            if salary_range:

                minimum = salary_range.get(
                    "min"
                )

                maximum = salary_range.get(
                    "max"
                )

                currency = salary_range.get(
                    "currency",
                    "",
                )

                interval = salary_range.get(
                    "interval",
                    "",
                )

                if (
                    minimum is not None
                    and maximum is not None
                ):
                    salary = (
                        f"{minimum}-{maximum} "
                        f"{currency} / {interval}"
                    )

            posted_date = self.parse_created_at(
                item.get("createdAt")
            )

            description = (
                self.extract_description(
                    item
                )
            )

            job = Job(
                job_title=item.get(
                    "text",
                    "",
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
                    "hostedUrl",
                    "",
                ),
                description=description,
                source_job_id=str(
                    item.get(
                        "id",
                        "",
                    )
                ),
            )

            jobs.append(job)

        return jobs