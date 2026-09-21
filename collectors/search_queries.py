from collectors.keyword_config import TARGET_JOB_TITLES


def build_search_queries():
    queries = []

    for job_family, titles in TARGET_JOB_TITLES.items():
        for title in titles:
            queries.append({
                "job_family": job_family,
                "query": title
            })

    return queries


if __name__ == "__main__":
    queries = build_search_queries()

    print(f"Total search queries: {len(queries)}")

    for item in queries[:20]:
        print(
            f"[{item['job_family']}] "
            f"{item['query']}"
        )
