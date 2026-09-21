from dataclasses import dataclass


@dataclass
class Job:

    job_title: str
    company: str = ""
    location: str = ""
    salary: str = ""
    posted_date: str = ""
    source: str = ""
    source_url: str = ""
    description: str = ""
    source_job_id: str = ""

    def to_dict(self):

        return {
            "job_title": self.job_title.strip(),
            "company": self.company.strip(),
            "location": self.location.strip(),
            "salary": self.salary.strip(),
            "posted_date": self.posted_date.strip(),
            "source": self.source.strip(),
            "source_url": self.source_url.strip(),
            "description": self.description.strip(),
            "source_job_id": self.source_job_id.strip(),
        }
