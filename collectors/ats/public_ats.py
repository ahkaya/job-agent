import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse

import requests

from collectors.base_collector import BaseCollector


class PublicATSCollector(BaseCollector):
    timeout = 20

    def request_json(self, url, method="GET", **kwargs):
        headers = {
            "User-Agent": "job-agent/1.0",
            "Accept": "application/json,text/plain,*/*",
        }
        headers.update(kwargs.pop("headers", {}))
        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=self.timeout,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()

    def request_text(self, url, **kwargs):
        response = requests.get(
            url,
            headers={
                "User-Agent": "job-agent/1.0",
                "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
            },
            timeout=self.timeout,
            **kwargs,
        )
        response.raise_for_status()
        return response.text

    def clean_html(self, value):
        if not value:
            return ""

        text = html.unescape(str(value))
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def first(self, data, *keys, default=""):
        if not isinstance(data, dict):
            return default

        for key in keys:
            value = data.get(key)
            if value not in (None, ""):
                return value

        return default

    def location_text(self, value):
        if isinstance(value, str):
            return value.strip()

        if isinstance(value, dict):
            parts = []

            for key in (
                "name",
                "city",
                "state",
                "province",
                "country",
                "country_name",
            ):
                item = value.get(key)
                if isinstance(item, dict):
                    item = (
                        item.get("name")
                        or item.get("label")
                        or item.get("name_en")
                    )

                if item:
                    parts.append(str(item).strip())

            return ", ".join(dict.fromkeys(parts))

        if isinstance(value, list):
            locations = [
                self.location_text(item)
                for item in value
            ]
            return " | ".join(
                item for item in locations if item
            )

        return ""

    def normalize_date(self, value):
        if not value:
            return ""

        value = str(value).strip()

        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return value

        candidates = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y",
        ]

        for fmt in candidates:
            try:
                return datetime.strptime(
                    value,
                    fmt,
                ).date().isoformat()
            except ValueError:
                pass

        match = re.search(
            r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})",
            value,
        )

        if match:
            year, month, day = match.groups()
            return (
                f"{int(year):04d}-"
                f"{int(month):02d}-"
                f"{int(day):02d}"
            )

        return ""

    def make_job(
        self,
        *,
        title,
        company,
        location="",
        salary="",
        posted_date="",
        url="",
        description="",
        source_job_id="",
    ):
        return self.normalize_job(
            {
                "job_title": str(title or "").strip(),
                "company": str(company or "").strip(),
                "location": str(location or "").strip(),
                "salary": str(salary or "").strip(),
                "posted_date": self.normalize_date(posted_date),
                "source_url": str(url or "").strip(),
                "description": self.clean_html(description),
                "source_job_id": str(
                    source_job_id or url or title or ""
                ),
            }
        )


class WorkableCollector(PublicATSCollector):
    source_name = "workable"

    def collect_company(self, board_token, company_name):
        slug = board_token.strip()

        urls = [
            (
                "https://apply.workable.com/"
                f"api/v1/widget/accounts/{slug}?details=true"
            ),
            (
                "https://apply.workable.com/"
                f"api/v1/widget/accounts/{slug}"
            ),
        ]

        data = None

        for url in urls:
            try:
                data = self.request_json(url)
                break
            except requests.RequestException:
                continue

        if data is None:
            return []

        raw_jobs = (
            data.get("jobs", [])
            if isinstance(data, dict)
            else data
        )

        jobs = []

        for item in raw_jobs or []:
            if not isinstance(item, dict):
                continue

            shortcode = self.first(
                item,
                "shortcode",
                "id",
            )

            title = self.first(
                item,
                "title",
                "full_title",
            )

            location = self.location_text(
                self.first(
                    item,
                    "location",
                    "locations",
                )
            )

            url = self.first(
                item,
                "url",
                "shortlink",
                "application_url",
            )

            if not url and shortcode:
                url = (
                    f"https://apply.workable.com/"
                    f"{slug}/j/{shortcode}/"
                )

            description = self.first(
                item,
                "description",
                "full_description",
                "job_description",
            )

            posted = self.first(
                item,
                "published",
                "published_at",
                "created_at",
            )

            jobs.append(
                self.make_job(
                    title=title,
                    company=company_name,
                    location=location,
                    salary=self.first(
                        item,
                        "salary",
                        "salary_range",
                    ),
                    posted_date=posted,
                    url=url,
                    description=description,
                    source_job_id=shortcode,
                )
            )

        return jobs


class RecruiteeCollector(PublicATSCollector):
    source_name = "recruitee"

    def collect_company(self, board_token, company_name):
        slug = board_token.strip()

        url = (
            f"https://{slug}.recruitee.com/"
            "api/offers/"
        )

        try:
            data = self.request_json(url)
        except requests.RequestException:
            return []

        offers = (
            data.get("offers", [])
            if isinstance(data, dict)
            else data
        )

        jobs = []

        for item in offers or []:
            if not isinstance(item, dict):
                continue

            title = self.first(item, "title", "name")
            offer_id = self.first(
                item,
                "id",
                "reference",
            )

            locations = (
                item.get("locations")
                or item.get("location")
            )

            location = self.location_text(locations)

            description = self.first(
                item,
                "description",
                "description_requirements",
            )

            url = self.first(
                item,
                "careers_url",
                "url",
            )

            if not url:
                slug_value = self.first(
                    item,
                    "slug",
                )
                if slug_value:
                    url = (
                        f"https://{slug}.recruitee.com/"
                        f"o/{slug_value}"
                    )

            jobs.append(
                self.make_job(
                    title=title,
                    company=company_name,
                    location=location,
                    salary=self.first(
                        item,
                        "salary",
                        "salary_text",
                    ),
                    posted_date=self.first(
                        item,
                        "created_at",
                        "published_at",
                    ),
                    url=url,
                    description=description,
                    source_job_id=offer_id,
                )
            )

        return jobs


class TeamtailorCollector(PublicATSCollector):
    source_name = "teamtailor"

    def collect_company(self, board_token, company_name):
        slug = board_token.strip()

        url = (
            f"https://{slug}.teamtailor.com/"
            "jobs.json"
        )

        try:
            data = self.request_json(url)
        except requests.RequestException:
            return []

        raw_jobs = (
            data.get("jobs", [])
            if isinstance(data, dict)
            else data
        )

        jobs = []

        for item in raw_jobs or []:
            if not isinstance(item, dict):
                continue

            title = self.first(
                item,
                "title",
                "name",
            )

            location = self.location_text(
                self.first(
                    item,
                    "location",
                    "locations",
                )
            )

            url = self.first(
                item,
                "url",
                "apply_url",
            )

            job_id = self.first(
                item,
                "id",
                "uuid",
            )

            jobs.append(
                self.make_job(
                    title=title,
                    company=company_name,
                    location=location,
                    salary=self.first(
                        item,
                        "salary",
                    ),
                    posted_date=self.first(
                        item,
                        "published_at",
                        "created_at",
                    ),
                    url=url,
                    description=self.first(
                        item,
                        "description",
                    ),
                    source_job_id=job_id,
                )
            )

        return jobs


class PersonioCollector(PublicATSCollector):
    source_name = "personio"

    def collect_company(self, board_token, company_name):
        slug = board_token.strip()

        url = (
            f"https://{slug}.jobs.personio.de/"
            "xml?language=en"
        )

        try:
            response = requests.get(
                url,
                headers={
                    "User-Agent": "job-agent/1.0",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except (
            requests.RequestException,
            ET.ParseError,
        ):
            return []

        jobs = []

        for item in root.findall(".//position"):
            def xml_value(name):
                node = item.find(f".//{name}")
                return (
                    node.text.strip()
                    if node is not None and node.text
                    else ""
                )

            title = (
                xml_value("name")
                or xml_value("title")
            )

            job_id = (
                xml_value("id")
                or xml_value("requisitionId")
            )

            location = (
                xml_value("office")
                or xml_value("location")
            )

            description = (
                xml_value("jobDescriptions")
                or xml_value("description")
            )

            url_value = (
                xml_value("jobAd")
                or xml_value("url")
            )

            posted = (
                xml_value("createdAt")
                or xml_value("publicationDate")
            )

            jobs.append(
                self.make_job(
                    title=title,
                    company=company_name,
                    location=location,
                    salary=xml_value("salary"),
                    posted_date=posted,
                    url=url_value,
                    description=description,
                    source_job_id=job_id,
                )
            )

        return jobs


class BambooHRCollector(PublicATSCollector):
    source_name = "bamboohr"

    def collect_company(self, board_token, company_name):
        slug = board_token.strip()

        base = (
            f"https://{slug}.bamboohr.com"
        )

        list_url = f"{base}/careers/list"

        try:
            data = self.request_json(list_url)
        except requests.RequestException:
            return []

        raw_jobs = (
            data.get("result", [])
            if isinstance(data, dict)
            else data
        )

        jobs = []

        for item in raw_jobs or []:
            if not isinstance(item, dict):
                continue

            job_id = self.first(
                item,
                "id",
                "jobOpeningId",
            )

            title = self.first(
                item,
                "jobOpeningName",
                "title",
            )

            location = self.location_text(
                item.get("location")
            )

            if not location:
                location = self.location_text(
                    item.get("atsLocation")
                )

            detail = {}

            if job_id:
                try:
                    detail = self.request_json(
                        f"{base}/careers/"
                        f"{job_id}/detail"
                    )
                except requests.RequestException:
                    detail = {}

            description = self.first(
                detail,
                "description",
                "jobDescription",
            )

            posted = self.first(
                detail,
                "datePosted",
                "postedDate",
            )

            url = self.first(
                detail,
                "shareUrl",
                "url",
            )

            if not url and job_id:
                url = (
                    f"{base}/careers/"
                    f"{job_id}"
                )

            jobs.append(
                self.make_job(
                    title=title,
                    company=company_name,
                    location=location,
                    salary=self.first(
                        detail,
                        "salary",
                        "compensation",
                    ),
                    posted_date=posted,
                    url=url,
                    description=description,
                    source_job_id=job_id,
                )
            )

        return jobs


class WorkdayCollector(PublicATSCollector):
    source_name = "workday"

    def collect_company(self, board_token, company_name):
        board_url = board_token.strip()

        parsed = urlparse(board_url)
        host = parsed.netloc

        if not host or ".myworkdayjobs.com" not in host:
            return []

        host_parts = host.split(".")
        tenant = host_parts[0]

        path_parts = [
            part
            for part in parsed.path.split("/")
            if part
        ]

        if "wday" in path_parts:
            return []

        site = path_parts[-1] if path_parts else ""

        if not site:
            return []

        endpoint = (
            f"https://{host}/wday/cxs/"
            f"{tenant}/{site}/jobs"
        )

        jobs = []
        offset = 0

        while True:
            payload = {
                "appliedFacets": {},
                "limit": 20,
                "offset": offset,
                "searchText": "",
            }

            try:
                data = self.request_json(
                    endpoint,
                    method="POST",
                    json=payload,
                    headers={
                        "User-Agent": "job-agent/1.0",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                )
            except requests.RequestException:
                break

            postings = data.get(
                "jobPostings",
                [],
            )

            if not postings:
                break

            for item in postings:
                title = self.first(
                    item,
                    "title",
                    "jobTitle",
                )

                location = self.location_text(
                    self.first(
                        item,
                        "locations",
                        "location",
                    )
                )

                url = self.first(
                    item,
                    "externalPath",
                    "url",
                )

                if url and url.startswith("/"):
                    url = (
                        f"https://{host}{url}"
                    )

                job_id = self.first(
                    item,
                    "bulletFields",
                    "id",
                )

                description = self.first(
                    item,
                    "description",
                    "jobDescription",
                )

                jobs.append(
                    self.make_job(
                        title=title,
                        company=company_name,
                        location=location,
                        posted_date=self.first(
                            item,
                            "postedDate",
                            "startDate",
                        ),
                        url=url,
                        description=description,
                        source_job_id=job_id,
                    )
                )

            total = data.get(
                "total",
                len(postings),
            )

            offset += len(postings)

            if offset >= total:
                break

            if len(postings) < 20:
                break

        return jobs


class BreezyCollector(PublicATSCollector):
    source_name = "breezy"

    def collect_company(self, board_token, company_name):
        slug = board_token.strip()

        url = (
            f"https://{slug}.breezy.hr/json"
        )

        try:
            data = self.request_json(url)
        except requests.RequestException:
            return []

        raw_jobs = (
            data if isinstance(data, list)
            else data.get("jobs", [])
        )

        jobs = []

        for item in raw_jobs or []:
            if not isinstance(item, dict):
                continue

            location = self.location_text(
                item.get("location")
            )

            jobs.append(
                self.make_job(
                    title=self.first(
                        item,
                        "name",
                        "title",
                    ),
                    company=company_name,
                    location=location,
                    salary=self.first(
                        item,
                        "salary",
                    ),
                    posted_date=self.first(
                        item,
                        "published_date",
                        "published_at",
                    ),
                    url=self.first(
                        item,
                        "url",
                    ),
                    description=self.first(
                        item,
                        "description",
                    ),
                    source_job_id=self.first(
                        item,
                        "id",
                        "url",
                    ),
                )
            )

        return jobs


class RipplingCollector(PublicATSCollector):
    source_name = "rippling"

    def collect_company(self, board_token, company_name):
        slug = board_token.strip()

        url = (
            "https://api.rippling.com/platform/api/"
            f"ats/v1/board/{slug}/jobs"
        )

        try:
            data = self.request_json(url)
        except requests.RequestException:
            return []

        raw_jobs = (
            data if isinstance(data, list)
            else data.get("jobs", [])
        )

        jobs = []

        for item in raw_jobs or []:
            if not isinstance(item, dict):
                continue

            location = self.location_text(
                item.get("workLocation")
                or item.get("location")
            )

            jobs.append(
                self.make_job(
                    title=self.first(
                        item,
                        "name",
                        "title",
                    ),
                    company=company_name,
                    location=location,
                    salary=self.first(
                        item,
                        "salary",
                    ),
                    posted_date=self.first(
                        item,
                        "postedAt",
                        "publishedAt",
                    ),
                    url=self.first(
                        item,
                        "url",
                    ),
                    description=self.first(
                        item,
                        "description",
                    ),
                    source_job_id=self.first(
                        item,
                        "uuid",
                        "id",
                        "url",
                    ),
                )
            )

        return jobs
