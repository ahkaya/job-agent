from collectors.job_schema import Job


class BaseCollector:
    source_name = ""

    def collect(self):
        raise NotImplementedError(
            "Source-specific collectors must implement collect()."
        )

    def normalize_job(self, job_data):
        return Job(
            job_title=job_data.get("job_title", ""),
            company=job_data.get("company", ""),
            location=job_data.get("location", ""),
            salary=job_data.get("salary", ""),
            posted_date=job_data.get("posted_date", ""),
            source=self.source_name,
            source_url=job_data.get("source_url", ""),
            description=job_data.get("description", ""),
            source_job_id=job_data.get("source_job_id", ""),
        )
