import os

from collectors.agencies.randstad import RandstadCollector
from collectors.agencies.tempo_team import TempoTeamCollector
from collectors.agencies.adecco import AdeccoCollector


def collect_agency_discovery():
    max_pages = int(
        os.environ.get(
            "JOB_AGENCY_MAX_PAGES",
            "2",
        )
    )

    print()
    print("=" * 50)
    print("DISCOVERY: RECRUITMENT AGENCIES")
    print("=" * 50)

    collectors = [
        RandstadCollector(),
        TempoTeamCollector(),
        AdeccoCollector(),
    ]

    all_jobs = []

    for collector in collectors:
        name = getattr(collector, "source_name", collector.__class__.__name__)
        print(f"\n--- {name} ---")
        try:
            jobs = collector.collect(max_pages=max_pages)
            print(f"{name}: {len(jobs)} jobs")
            all_jobs.extend(jobs)
        except Exception as error:
            print(f"{name} collector error: {error}")

    print(f"\nAgency discovery total: {len(all_jobs)}")
    return all_jobs
