from datetime import datetime


def create_job_input(
    job_title,
    company="",
    location="",
    salary="",
    posted_date="",
    source="",
    source_url="",
    description=""
):
    return {
        "job_title": job_title.strip(),
        "company": company.strip(),
        "location": location.strip(),
        "salary": salary.strip(),
        "posted_date": posted_date.strip(),
        "source": source.strip(),
        "source_url": source_url.strip(),
        "description": description.strip(),
        "date_found": datetime.now().strftime("%Y-%m-%d")
    }
def is_within_30_days(posted_date):
    if not posted_date:
        return None

    try:
        posted = datetime.strptime(posted_date, "%Y-%m-%d").date()
        today = datetime.now().date()

        age = (today - posted).days

        return 0 <= age <= 30

    except ValueError:
        return None
