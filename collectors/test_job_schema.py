from collectors.job_schema import Job


def test_job_to_dict_strips_text_fields():
    job = Job(
        job_title="  Business Operations Specialist  ",
        company=" Test Company ",
        location=" Amsterdam, Netherlands ",
        salary=" €3,000 ",
        posted_date=" 2026-09-18 ",
        source=" greenhouse ",
        source_url=" https://example.com/job/123 ",
        description=" Operations coordination. ",
        source_job_id=" 123 ",
    )

    assert job.to_dict() == {
        "job_title": "Business Operations Specialist",
        "company": "Test Company",
        "location": "Amsterdam, Netherlands",
        "salary": "€3,000",
        "posted_date": "2026-09-18",
        "source": "greenhouse",
        "source_url": "https://example.com/job/123",
        "description": "Operations coordination.",
        "source_job_id": "123",
    }


def test_job_to_dict_preserves_all_source_fields():
    job = Job(
        job_title="Business Analyst",
        company="Example",
        location="Utrecht, Netherlands",
        source="lever",
        source_url="https://example.com/abc",
        description="Full job description",
        source_job_id="abc",
    )

    data = job.to_dict()

    assert set(data) == {
        "job_title",
        "company",
        "location",
        "salary",
        "posted_date",
        "source",
        "source_url",
        "description",
        "source_job_id",
    }


def test_job_defaults_are_empty_strings():
    job = Job(job_title="Business Analyst")

    data = job.to_dict()

    assert data["company"] == ""
    assert data["location"] == ""
    assert data["salary"] == ""
    assert data["source"] == ""
    assert data["source_url"] == ""
    assert data["description"] == ""
    assert data["source_job_id"] == ""
