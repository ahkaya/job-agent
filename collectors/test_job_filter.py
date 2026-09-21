from dataclasses import dataclass

from collectors.job_filter import (
    filter_jobs,
    is_blacklisted_title,
    is_excluded_engineer_role,
    is_excluded_seniority,
    is_fully_remote,
)


@dataclass
class JobFixture:
    job_title: str
    location: str
    posted_date: str
    description: str = ""


def test_blacklisted_title():
    assert is_blacklisted_title("Call Center Agent")
    assert not is_blacklisted_title("Business Operations Specialist")


def test_excluded_seniority():
    assert is_excluded_seniority("Senior Business Analyst")
    assert not is_excluded_seniority("Junior Business Analyst")


def test_engineer_filter():
    assert is_excluded_engineer_role("Software Engineer")
    assert not is_excluded_engineer_role("Business Analyst")


def test_fully_remote():
    job = JobFixture(
        job_title="Business Operations Specialist",
        location="Remote",
        posted_date="2026-09-18",
    )
    assert is_fully_remote(job)


def test_netherlands_job_is_kept():
    job = JobFixture(
        job_title="Junior Business Operations Specialist",
        location="Amsterdam, Netherlands",
        posted_date="2026-09-18",
    )

    filtered, stats = filter_jobs([job])

    assert len(filtered) == 1
    assert stats["kept"] == 1


def test_foreign_job_is_removed():
    job = JobFixture(
        job_title="Business Operations Specialist",
        location="Berlin, Germany",
        posted_date="2026-09-18",
    )

    filtered, stats = filter_jobs([job])

    assert len(filtered) == 0
    assert stats["wrong_location"] == 1


def test_old_job_is_removed():
    job = JobFixture(
        job_title="Business Operations Specialist",
        location="Amsterdam, Netherlands",
        posted_date="2020-01-01",
    )

    filtered, stats = filter_jobs([job])

    assert len(filtered) == 0
    assert stats["too_old"] == 1


def test_non_nl_location_is_not_kept():
    job = JobFixture(
        job_title="Business Operations Specialist",
        location="Somewhere Unknown",
        posted_date="2026-09-18",
    )

    filtered, stats = filter_jobs([job])

    assert len(filtered) == 0
    assert stats["wrong_location"] == 1
