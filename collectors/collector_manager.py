import yaml

from collectors.ats.detect import detect_ats
from collectors.ats.greenhouse import GreenhouseCollector
from collectors.ats.lever import LeverCollector
from collectors.ats.ashby import AshbyCollector
from collectors.job_filter import filter_jobs
from data.database import create_tables, insert_collected_job


REGISTRY_PATH = "config/company_registry.yaml"


def load_company_registry():
    with open(REGISTRY_PATH, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    return data.get("companies", [])


def save_jobs_to_database(jobs):
    for job in jobs:

        job_id, is_new = insert_collected_job(job)

        if is_new:
            print(
                f"DB INSERT: {job.company} | "
                f"{job.job_title} | ID={job_id}"
            )
        else:
            print(
                f"DB DUPLICATE: {job.company} | "
                f"{job.job_title} | ID={job_id}"
            )


def collect_from_registry():
    create_tables()

    companies = load_company_registry()
    all_jobs = []

    greenhouse_collector = GreenhouseCollector()
    lever_collector = LeverCollector()
    ashby_collector = AshbyCollector()

    for company in companies:

        if not company.get("active", False):
            continue

        name = company.get("name", "")
        careers_url = company.get("careers_url", "")
        configured_ats = company.get("ats", "")
        configured_board_token = company.get(
            "board_token",
            ""
        )

        print()
        print("=" * 50)
        print(f"COMPANY: {name}")
        print(f"CAREERS URL: {careers_url}")

        try:

            if (
                configured_ats in (
                    "greenhouse",
                    "lever",
                    "ashby",
                )
                and configured_board_token
            ):

                detected = {
                    "ats": configured_ats,
                    "board_token": configured_board_token,
                }

                print(
                    "ATS CONFIGURED:",
                    detected
                )

            else:

                detected = detect_ats(careers_url)

                print(
                    "ATS DETECTED:",
                    detected
                )

            if not detected:
                print("No supported ATS detected.")
                continue

            ats = detected.get("ats")
            board_token = detected.get("board_token")

            if ats == "greenhouse":

                jobs = greenhouse_collector.collect_company(
                    board_token=board_token,
                    company_name=name,
                )

            elif ats == "lever":

                jobs = lever_collector.collect_company(
                    board_token=board_token,
                    company_name=name,
                )

            elif ats == "ashby":

                jobs = ashby_collector.collect_company(
                    board_token=board_token,
                    company_name=name,
                )

            else:

                print(
                    f"ATS '{ats}' is detected "
                    "but not implemented yet."
                )
                continue

            print(f"RAW JOBS: {len(jobs)}")

            filtered_jobs, statistics = filter_jobs(
                jobs
            )

            print()
            print("FILTER RESULTS")
            print("-" * 50)

            for key, value in statistics.items():
                print(f"{key}: {value}")

            save_jobs_to_database(filtered_jobs)

            all_jobs.extend(filtered_jobs)

        except Exception as error:

            print(
                f"COLLECTOR ERROR: {error}"
            )

    return all_jobs


if __name__ == "__main__":

    jobs = collect_from_registry()

    print()
    print("=" * 50)
    print("FINAL FILTERED JOBS")
    print("=" * 50)
    print(len(jobs))

    for job in jobs[:10]:

        print()
        print(f"Title: {job.job_title}")
        print(f"Company: {job.company}")
        print(f"Location: {job.location}")
        print(f"Posted: {job.posted_date}")
        print(f"Source ID: {job.source_job_id}")
