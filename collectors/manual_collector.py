from data.job_input import create_job_input


def collect_manual_job():
    print("\nMANUAL JOB COLLECTOR")
    print("--------------------")
    print("Paste the job information using this format:")
    print("")
    print("Job title: ...")
    print("Company: ...")
    print("Location: ...")
    print("Salary: ...")
    print("Posted date: YYYY-MM-DD")
    print("Source: ...")
    print("Source URL: ...")
    print("")
    print("Then paste the full job description.")
    print("When finished, press Control+D on a new line.")
    print("")

    import sys

    raw_input = sys.stdin.read().strip()

    lines = raw_input.splitlines()

    data = {
        "job_title": "",
        "company": "",
        "location": "",
        "salary": "",
        "posted_date": "",
        "source": "",
        "source_url": "",
    }

    description_lines = []
    in_description = False

    field_map = {
        "job title": "job_title",
        "company": "company",
        "location": "location",
        "salary": "salary",
        "posted date": "posted_date",
        "source": "source",
        "source url": "source_url",
    }

    for line in lines:
        stripped = line.strip()

        if not in_description and ":" in stripped:
            field_name, value = stripped.split(":", 1)
            field_name = field_name.strip().lower()
            value = value.strip()

            if field_name in field_map:
                data[field_map[field_name]] = value
                continue

        in_description = True

        if stripped:
            description_lines.append(stripped)

    description = "\n".join(description_lines)

    return create_job_input(
        job_title=data["job_title"],
        company=data["company"],
        location=data["location"],
        salary=data["salary"],
        posted_date=data["posted_date"],
        source=data["source"],
        source_url=data["source_url"],
        description=description
    )


if __name__ == "__main__":
    job = collect_manual_job()

    print("\n===== COLLECTED JOB =====")
    print(job)
