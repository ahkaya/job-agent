import html
import re
from datetime import datetime

import requests

from collectors.job_schema import Job
from collectors.base_collector import BaseCollector


class GreenhouseCollector(BaseCollector):

    source_name = "Greenhouse"

    BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

    def build_url(self, board_token):
        return f"{self.BASE_URL}/{board_token}/jobs?content=true"

    def strip_html(self, text):
        if not text:
            return ""

        text = html.unescape(text)

        text = re.sub(
            r"<br\s*/?>",
            "\n",
            text,
            flags=re.IGNORECASE
        )

        text = re.sub(
            r"</p\s*>",
            "\n",
            text,
            flags=re.IGNORECASE
        )

        text = re.sub(
            r"<[^>]+>",
            " ",
            text
        )

        text = re.sub(
            r"\n\s*\n+",
            "\n\n",
            text
        )

        text = re.sub(
            r"[ \t]+",
            " ",
            text
        )

        return text.strip()

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

    def collect_company(self, board_token, company_name=None):
        url = self.build_url(board_token)

        response = requests.get(
            url,
            timeout=20
        )

        response.raise_for_status()

        data = response.json()

        jobs = []

        for item in data.get("jobs", []):

            location = (
                item.get("location", {})
                .get("name", "")
            )

            description = self.strip_html(
                item.get("content", "")
            )

            posted_date = self.parse_date(
                item.get("first_published")
            )

            job = Job(
                job_title=item.get("title", ""),
                company=(
                    company_name
                    if company_name
                    else board_token
                ),
                location=location,
                posted_date=posted_date,
                source=self.source_name,
                source_url=item.get(
                    "absolute_url",
                    ""
                ),
                description=description,
                source_job_id=str(
                    item.get("id", "")
                ),
            )

            jobs.append(job)

        return jobs


if __name__ == "__main__":

    collector = GreenhouseCollector()

    jobs = collector.collect_company(
        board_token="stripe",
        company_name="Stripe"
    )

    print("\nGREENHOUSE API TEST")
    print("-------------------")
    print(f"Jobs collected: {len(jobs)}")

    for job in jobs[:10]:

        print()
        print(f"ID: {job.source_job_id}")
        print(f"Title: {job.job_title}")
        print(f"Company: {job.company}")
        print(f"Location: {job.location}")
        print(f"Posted: {job.posted_date}")
        print(f"URL: {job.source_url}")
        print(f"Description length: {len(job.description)}")
