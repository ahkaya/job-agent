import sqlite3
from dataclasses import dataclass
from pathlib import Path

import data.database as database
from collectors.job_filter import filter_jobs


@dataclass
class JobFixture:
    job_title: str
    company: str
    location: str
    posted_date: str
    source: str
    source_job_id: str
    source_url: str
    description: str = ""
    salary: str = ""


def test_filtered_job_is_saved_and_deduplicated(tmp_path, monkeypatch):
    db_path = tmp_path / "test_jobs.db"

    monkeypatch.setattr(database, "DB_PATH", db_path)
    database.create_tables()

    job = JobFixture(
        job_title="Junior Business Operations Specialist",
        company="Integration Test Company",
        location="Amsterdam, Netherlands",
        posted_date="2026-09-18",
        source="greenhouse",
        source_job_id="test-123",
        source_url="https://example.com/jobs/test-123",
        description="Operations coordination and reporting.",
    )

    filtered, stats = filter_jobs([job])

    assert len(filtered) == 1
    assert stats["kept"] == 1

    first_id, first_new = database.insert_collected_job(filtered[0])

    assert first_new is True

    second_id, second_new = database.insert_collected_job(filtered[0])

    assert second_id == first_id
    assert second_new is False

    conn = sqlite3.connect(db_path)

    job_count = conn.execute(
        "SELECT COUNT(*) FROM jobs"
    ).fetchone()[0]

    source_count = conn.execute(
        "SELECT COUNT(*) FROM job_sources"
    ).fetchone()[0]

    source_row = conn.execute(
        """
        SELECT job_id, source, source_job_id
        FROM job_sources
        """
    ).fetchone()

    conn.close()

    assert job_count == 1
    assert source_count == 1
    assert source_row == (
        first_id,
        "greenhouse",
        "test-123",
    )
