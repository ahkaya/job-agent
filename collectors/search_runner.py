from collectors.search_queries import build_search_queries


def get_all_search_queries():
    return build_search_queries()


def print_search_plan():
    queries = get_all_search_queries()

    families = {}

    for item in queries:
        family = item["job_family"]
        families.setdefault(family, 0)
        families[family] += 1

    print("\nJOB SEARCH PLAN")
    print("---------------")
    print(f"Total queries: {len(queries)}")
    print()

    for family, count in families.items():
        print(f"{family}: {count}")


if __name__ == "__main__":
    print_search_plan()
