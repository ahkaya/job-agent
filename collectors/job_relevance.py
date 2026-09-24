def normalize_text(text):
    return " ".join(str(text or "").lower().split())


HARD_NEGATIVE_PATTERNS = [
    "monteur",
    "machinist",

    "shovelmachinist",
    "walsmachinist",
    "grond- en groenwerker",
    "constructeur",
    "modelleur",
    "tekenaar",
    "software developer",
    "electronic technician",
    "salvage diver",
    "tax specialist",
    "hoofduitvoerder",
    "uitvoerder",
    "voorman",
    "vakman",
    "technisch inspecteur",
    "veiligheidsfunctionaris",
    "q hse",
    "qhse",
    "wegontwerper",
    "ontwerpleider",
    "calculator",
    "werkstudent",
    "gemeente",
]

INFRASTRUCTURE_CONTEXT = [
    "verhardingen",
    "wegenbouw",
    "wegen en",
    "bouwteams",
    "civiel",
    "gww",
    "infratechniek",
    "leidingbouw",
    "spoor",
    "betonbouw",
    "betonconstructies",
    "asfalt",
    "kunstwerken",
    "kabels en leidingen",
    "water & transportleidingen",
    "tijdelijke verkeersmaatregelen",
]

WAREHOUSE_PATTERNS = [
    "heftruck",
    "forklift",
    "magazijnmedewerker",
    "warehouse",
    "orderpicker",
    "order picker",
    "warehouse operator",
    "warehouse worker",
    "logistics worker",
    "inventory",
    "stock medewerker",
    "distributie medewerker",
    "fulfilment",
    "fulfillment",
]

BIM_PATTERNS = [
    "bim",
]

WORK_PREPARATION_PATTERNS = [
    "werkvoorbereider",
]

CLEAR_TARGET_PATTERNS = [
    "business analyst",
    "business operations",
    "operations specialist",
    "operations coordinator",
    "operations support",
    "projectcoördinator",
    "project coordinator",
    "pmo",
    "functioneel beheerder",
    "business central",
    "supply chain",
    "logistics",
    "procurement",
    "purchasing",
    "marketing",
    "communication",
    "content creation",
    "international trade",
    "commercial",
    "research",
    "data",
    "analytics",
    "emvi",
    "projectleider",
    "incident management",
]

from collectors.keyword_config import DUTCH_TARGET_PATTERNS


AMBIGUOUS_PATTERNS = [
    "adviseur",
]


def relevance_class(job_title):
    title = normalize_text(job_title)

    if not title:
        return "UNKNOWN"

    if any(pattern in title for pattern in WAREHOUSE_PATTERNS):
        return "POTENTIALLY_RELEVANT"

    if any(pattern in title for pattern in HARD_NEGATIVE_PATTERNS):
        return "UNRELATED"

    if any(pattern in title for pattern in INFRASTRUCTURE_CONTEXT):
        return "UNRELATED"

    if any(pattern in title for pattern in BIM_PATTERNS):
        return "UNRELATED"

    if any(pattern in title for pattern in WORK_PREPARATION_PATTERNS):
        return "UNRELATED"

    # Expanded Dutch/English target patterns
    if any(pattern in title for pattern in DUTCH_TARGET_PATTERNS):
        return "POTENTIALLY_RELEVANT"

    if any(pattern in title for pattern in CLEAR_TARGET_PATTERNS):
        return "POTENTIALLY_RELEVANT"

    if any(pattern in title for pattern in AMBIGUOUS_PATTERNS):
        return "AMBIGUOUS"

    return "UNRELATED"


def is_potentially_relevant(job_title):
    return relevance_class(job_title) != "UNRELATED"
