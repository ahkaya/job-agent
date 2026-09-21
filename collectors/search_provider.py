from dataclasses import dataclass


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""


class SearchProvider:
    """
    Common interface for web-based job discovery.

    A concrete provider should implement search().
    """

    name = ""

    def search(self, query, max_results=10):
        raise NotImplementedError(
            "Search providers must implement search()."
        )
