import json
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from collectors.agencies.base import BaseAgencyCollector
from collectors.job_schema import Job


class RandstadCollector(BaseAgencyCollector):
    source_name = "Randstad"
    base_url = "https://www.randstad.nl/vacatures"

    def __init__(self, timeout=20):
        super().__init__(timeout=timeout)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "job-agent/1.0",
            "Accept": "text/html,application/xhtml+xml",
        })

    def _get(self, url, params=None):
        response = self.session.get(
            url,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.text

    def _extract_links(self, soup):
        links = []

        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "").strip()

            if not href:
                continue

            absolute = urljoin(
                self.base_url,
                href,
            )

            path = absolute.split("?", 1)[0].rstrip("/")

            if not re.search(r"/vacatures/\d+/[^/]+$", path):
                continue

            title = self.clean_text(
                anchor.get_text(" ", strip=True)
            )

            if not title:
                continue

            links.append((absolute, title))

        return links

    def _is_probable_job_link(self, url, title):
        import re

        path = url.split("?", 1)[0].rstrip("/")

        return bool(
            re.search(
                r"/vacatures/\d+/[^/]+$",
                path,
            )
        ) and len(title) >= 3

    def _extract_cards(self, soup):
        """
        Extract job cards from the search result page.

        Randstad has changed its frontend markup over time, so this
        intentionally uses link-based discovery instead of relying on
        one CSS class.
        """
        jobs = []
        seen = set()

        for url, anchor_title in self._extract_links(soup):

            if not self._is_probable_job_link(
                url,
                anchor_title,
            ):
                continue

            if url in seen:
                continue

            seen.add(url)

            container = None
            anchor = soup.find(
                "a",
                href=lambda value: value
                and urljoin(self.base_url, value) == url,
            )

            if anchor:
                container = (
                    anchor.find_parent(
                        ["article", "li"]
                    )
                    or anchor.parent
                )

            text = self.clean_text(
                container.get_text(" ", strip=True)
                if container
                else anchor_title
            )

            jobs.append({
                "url": url,
                "title": anchor_title,
                "text": text,
            })

        return jobs

    def _parse_detail(self, url):
        try:
            html = self._get(url)
        except requests.RequestException as error:
            print(f"  Randstad detail error: {url} -> {error}")
            return {}

        soup = BeautifulSoup(html, "html.parser")

        fallback_company = ""
        meta = soup.find("meta", attrs={"name": "description"})
        if meta:
            meta_text = self.clean_text(meta.get("content", ""))
            match = re.search(
                r"\bbij\s+(.+?)(?:\s+in\s+|\s*$)",
                meta_text,
                re.IGNORECASE,
            )
            if match:
                fallback_company = self.clean_text(match.group(1))

        return self.parse_json_ld_jobposting(
            soup,
            fallback_company=fallback_company,
        )

    def collect(self, max_pages=3):
        jobs = []
        seen_urls = set()

        for page in range(1, max_pages + 1):

            params = {}

            if page > 1:
                params["pagina"] = page

            print(
                f"  Randstad page {page}"
            )

            try:
                html = self._get(
                    self.base_url,
                    params=params,
                )
            except requests.RequestException as error:
                print(
                    f"  Randstad page error: {error}"
                )
                break

            soup = BeautifulSoup(
                html,
                "html.parser",
            )

            cards = self._extract_cards(soup)

            if not cards:
                print(
                    "  No job links found; stopping."
                )
                break

            page_new = 0

            for card in cards:

                url = card["url"]

                if url in seen_urls:
                    continue

                seen_urls.add(url)

                detail = self._parse_detail(url)

                title = (
                    detail.get("title")
                    or card["title"]
                )

                if not title:
                    continue

                description = (
                    detail.get("description")
                    or card["text"]
                )

                jobs.append(
                    Job(
                        job_title=title,
                        company=detail.get("company", ""),
                        location=detail.get("location", ""),
                        salary=detail.get("salary", ""),
                        posted_date=detail.get("posted_date", ""),
                        source=self.source_name,
                        source_url=url,
                        description=description,
                        source_job_id=self.make_source_job_id(
                            url
                        ),
                    )
                )

                page_new += 1

            print(
                f"  New jobs: {page_new}"
            )

            if page_new == 0:
                break

        print(
            f"Randstad total collected: {len(jobs)}"
        )

        return jobs
