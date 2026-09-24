from collectors.base_collector import BaseCollector
from collectors.discovery_utils import (
    normalize_url,
    resolve_posted_date,
    source_job_id,
    parse_json_ld_jobposting,
)


class BaseAgencyCollector(BaseCollector):
    source_type = "recruitment_agency"
    base_url = ""

    def __init__(self, timeout=20):
        self.timeout = timeout

    def normalize_url(self, url):
        return normalize_url(url)

    def resolve_posted_date(self, value):
        return resolve_posted_date(value)

    def make_source_job_id(self, url):
        return source_job_id(self.source_name, url)

    def clean_text(self, value):
        return " ".join(
            str(value or "").split()
        ).strip()

    def parse_json_ld_jobposting(self, soup, fallback_company=""):
        return parse_json_ld_jobposting(
            soup,
            fallback_company=fallback_company,
        )
