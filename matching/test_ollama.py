from matching.ollama_matcher import analyze_job_local
from collectors.ats.lever import LeverCollector


def get_test_job():

    collector = LeverCollector()

    jobs = collector.collect_company(
        board_token="arcteryx.com",
        company_name="ARC'TERYX",
    )

    for job in jobs:

        if "Wholesale Merchandise Planner" in job.job_title:
            return job.to_dict()

    raise RuntimeError(
        "Test job not found."
    )


if __name__ == "__main__":

    job = get_test_job()

    print()
    print("=" * 60)
    print("OLLAMA / QWEN MATCHING TEST")
    print("=" * 60)

    print(
        f"Title: {job['job_title']}"
    )

    print(
        f"Company: {job['company']}"
    )

    print(
        f"Location: {job['location']}"
    )

    print(
        f"Posted: {job['posted_date']}"
    )

    print(
        f"Description length: "
        f"{len(job['description'])}"
    )

    print()
    print(
        "Sending job to Qwen3 8B..."
    )

    analysis = analyze_job_local(
        job
    )

    print()
    print("=" * 60)
    print("LOCAL LLM RESULT")
    print("=" * 60)

    print(
        f"Match Category: "
        f"{analysis.get('match_category', '')}"
    )

    print(
        f"Job Family: "
        f"{analysis.get('job_family', '')}"
    )

    print(
        f"Seniority: "
        f"{analysis.get('seniority', '')}"
    )

    print()
    print("WHY MATCH:")

    for item in analysis.get(
        "why_match",
        [],
    ):
        print(f"- {item}")

    print()
    print("DIRECT MATCHES:")

    for item in analysis.get(
        "direct_matches",
        [],
    ):
        print(f"- {item}")

    print()
    print("TRANSFERABLE MATCHES:")

    for item in analysis.get(
        "transferable_matches",
        [],
    ):
        print(f"- {item}")

    print()
    print("GAPS:")

    for item in analysis.get(
        "gaps",
        [],
    ):
        print(f"- {item}")

    print()
    print("EXPERIENCE GAP:")

    print(
        analysis.get(
            "experience_gap",
            "",
        )
    )

    print()
    print("=" * 60)