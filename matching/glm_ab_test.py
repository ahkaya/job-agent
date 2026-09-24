import json
import os
import sqlite3
from datetime import datetime

from openai import OpenAI

from matching.gemini_matcher import (
    load_matching_config,
    build_matching_prompt,
)


DB_PATH = "data/jobs.db"
OUTPUT_PATH = "data/glm_ab_results.json"

TEST_JOB_IDS = [8, 15, 16, 17, 22]


def load_jobs():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        placeholders = ",".join("?" for _ in TEST_JOB_IDS)

        rows = conn.execute(
            f"""
            SELECT
                job_id,
                job_title,
                company,
                location,
                salary,
                posted_date,
                job_description
            FROM jobs
            WHERE job_id IN ({placeholders})
            ORDER BY job_id
            """,
            TEST_JOB_IDS,
        ).fetchall()

        jobs = []

        for row in rows:
            jobs.append({
                "job_id": row["job_id"],
                "job_title": row["job_title"],
                "company": row["company"],
                "location": row["location"],
                "salary": row["salary"],
                "posted_date": row["posted_date"],
                "job_description": row["job_description"],
            })

        return jobs

    finally:
        conn.close()


def run_glm(job, master_profile, matching_rules):
    prompt = build_matching_prompt(
        job,
        master_profile,
        matching_rules,
    )

    client = OpenAI(
        api_key=os.environ["GLM_API_KEY"],
        base_url="https://api.z.ai/api/paas/v4/",
    )

    response = client.chat.completions.create(
        model="glm-5.3-flash",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=0,
    )

    raw_response = response.choices[0].message.content.strip()

    try:
        analysis = json.loads(raw_response)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"GLM returned invalid JSON: {error}"
        ) from error

    usage = None

    if response.usage:
        usage = {
            "prompt_tokens": getattr(
                response.usage,
                "prompt_tokens",
                None,
            ),
            "completion_tokens": getattr(
                response.usage,
                "completion_tokens",
                None,
            ),
            "total_tokens": getattr(
                response.usage,
                "total_tokens",
                None,
            ),
        }

    return analysis, usage, raw_response


def main():
    if not os.environ.get("GLM_API_KEY"):
        raise RuntimeError(
            "GLM_API_KEY is not set."
        )

    master_profile, matching_rules = load_matching_config()
    jobs = load_jobs()

    expected_ids = set(TEST_JOB_IDS)
    actual_ids = {job["job_id"] for job in jobs}

    missing_ids = expected_ids - actual_ids

    if missing_ids:
        raise RuntimeError(
            f"Missing test jobs in database: {sorted(missing_ids)}"
        )

    results = []

    print("=" * 70)
    print("GLM-5.3-FLASH A/B TEST")
    print("=" * 70)
    print(f"Jobs: {TEST_JOB_IDS}")
    print()

    for index, job in enumerate(jobs, start=1):
        print(
            f"[{index}/5] "
            f"{job['job_id']} | "
            f"{job['company']} | "
            f"{job['job_title']}"
        )

        started_at = datetime.now().isoformat()

        try:
            analysis, usage, raw_response = run_glm(
                job,
                master_profile,
                matching_rules,
            )

            result = {
                "job_id": job["job_id"],
                "job_title": job["job_title"],
                "company": job["company"],
                "model": "glm-5.3-flash",
                "status": "success",
                "started_at": started_at,
                "finished_at": datetime.now().isoformat(),
                "usage": usage,
                "analysis": analysis,
                "raw_response": raw_response,
            }

            results.append(result)

            print(
                f"    Match: "
                f"{analysis.get('match_category', '')}"
            )
            print(
                f"    Priority: "
                f"{analysis.get('priority', '')}"
            )
            if usage:
                print(
                    f"    Tokens: "
                    f"{usage.get('total_tokens')}"
                )

        except Exception as error:
            result = {
                "job_id": job["job_id"],
                "job_title": job["job_title"],
                "company": job["company"],
                "model": "glm-5.3-flash",
                "status": "error",
                "started_at": started_at,
                "finished_at": datetime.now().isoformat(),
                "error": str(error),
            }

            results.append(result)

            print(f"    ERROR: {error}")

    output = {
        "test_model": "glm-5.3-flash",
        "test_job_ids": TEST_JOB_IDS,
        "created_at": datetime.now().isoformat(),
        "results": results,
    }

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2,
        )

    successful = sum(
        result["status"] == "success"
        for result in results
    )

    failed = len(results) - successful

    print()
    print("=" * 70)
    print("GLM TEST COMPLETE")
    print("=" * 70)
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
