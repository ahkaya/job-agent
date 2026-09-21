import re
import unicodedata


NL_CITIES = {
    "alkmaar",
    "almelo",
    "almere",
    "amersfoort",
    "amstelveen",
    "amsterdam",
    "apeldoorn",
    "arnhem",
    "assen",
    "breda",
    "delft",
    "deventer",
    "doetinchem",
    "dordrecht",
    "eindhoven",
    "enschede",
    "geleen",
    "goes",
    "gouda",
    "groningen",
    "haarlem",
    "harderwijk",
    "heerlen",
    "helmond",
    "hengelo",
    "hilversum",
    "hoofddorp",
    "hoorn",
    "leeuwarden",
    "leiden",
    "lelystad",
    "maastricht",
    "middelburg",
    "nijmegen",
    "oss",
    "roermond",
    "roosendaal",
    "rotterdam",
    "s-hertogenbosch",
    "schiedam",
    "sittard",
    "spijkenisse",
    "terneuzen",
    "tilburg",
    "utrecht",
    "veenendaal",
    "venlo",
    "vlissingen",
    "wageningen",
    "zaandam",
    "zeist",
    "zoetermeer",
    "zutphen",
    "zwolle",
}


NL_PROVINCES = {
    "drenthe",
    "flevoland",
    "friesland",
    "gelderland",
    "groningen",
    "limburg",
    "north holland",
    "noord holland",
    "north brabant",
    "noord brabant",
    "overijssel",
    "south holland",
    "zuid holland",
    "utrecht",
    "zeeland",
}


NL_COUNTRY_TERMS = {
    "netherlands",
    "the netherlands",
    "nederland",
    "nl",
    "nld",
}


NON_NL_COUNTRIES = {
    "argentina",
    "australia",
    "austria",
    "belgium",
    "brazil",
    "bulgaria",
    "canada",
    "chile",
    "china",
    "croatia",
    "czech republic",
    "czechia",
    "denmark",
    "estonia",
    "finland",
    "france",
    "germany",
    "greece",
    "hungary",
    "india",
    "ireland",
    "israel",
    "italy",
    "japan",
    "latvia",
    "lithuania",
    "luxembourg",
    "malaysia",
    "mexico",
    "new zealand",
    "norway",
    "philippines",
    "poland",
    "portugal",
    "romania",
    "serbia",
    "singapore",
    "slovakia",
    "slovenia",
    "south africa",
    "south korea",
    "spain",
    "sweden",
    "switzerland",
    "taiwan",
    "thailand",
    "united kingdom",
    "united states",
    "usa",
    "us",
    "u k",
    "uk",
    "u s",
    "u s a",
}


REMOTE_TERMS = {
    "remote",
    "fully remote",
    "work from anywhere",
    "work anywhere",
    "anywhere",
}


REGIONAL_TERMS = {
    "apac",
    "asia",
    "asia pacific",
    "benelux",
    "emea",
    "europe",
    "european union",
    "eu",
    "latin america",
    "latam",
    "north america",
    "northern europe",
    "southern europe",
    "western europe",
}


def normalize(text):
    text = unicodedata.normalize(
        "NFKC",
        str(text or ""),
    ).lower()

    # Location values arrive with inconsistent separators, such as
    # "Amsterdam / Hybrid", "Amsterdam, NL", and "U.S.A.".
    # Convert separators to spaces so country and place terms can be
    # matched consistently with word boundaries.
    text = re.sub(
        r"[^\w]+",
        " ",
        text,
        flags=re.UNICODE,
    )

    return " ".join(text.split())


def contains_term(text, term):
    return bool(
        re.search(
            r"\b" + re.escape(term) + r"\b",
            text,
        )
    )


def classify_location(location):
    """
    Classify a job location for the Netherlands job search.

    CONFIRMED_NL:
        Clearly identifiable Dutch location.

    NOT_NL:
        Clearly outside the Netherlands or explicitly remote.

    REGIONAL_AMBIGUOUS:
        Regional/multi-country location that cannot safely
        be treated as a Dutch physical/hybrid position.

    UNKNOWN:
        Location exists but cannot be classified confidently.
    """

    text = normalize(location)

    if not text:
        return "UNKNOWN"

    # ---------------------------------------------------------
    # 1. Remote jobs are ALWAYS excluded.
    # ---------------------------------------------------------

    if any(
        contains_term(text, term)
        for term in REMOTE_TERMS
    ):
        return "NOT_NL"

    # ---------------------------------------------------------
    # 2. Explicit country and regional detection.
    #
    # A country signal is more reliable than a city name. We deliberately
    # do not maintain a worldwide city list: many city names are ambiguous,
    # and an unverified foreign city should remain UNKNOWN.
    # ---------------------------------------------------------

    nl_country_match = any(
        contains_term(text, country)
        for country in NL_COUNTRY_TERMS
    )

    foreign_country_match = any(
        contains_term(text, country)
        for country in NON_NL_COUNTRIES
    )

    regional_match = any(
        contains_term(text, term)
        for term in REGIONAL_TERMS
    )

    if regional_match or (
        nl_country_match and foreign_country_match
    ):
        return "REGIONAL_AMBIGUOUS"

    if foreign_country_match:
        return "NOT_NL"

    # ---------------------------------------------------------
    # 3. Dutch country / city / province detection.
    # ---------------------------------------------------------

    if nl_country_match:
        return "CONFIRMED_NL"

    if any(
        contains_term(text, city)
        for city in NL_CITIES
    ) or any(
        contains_term(text, province)
        for province in NL_PROVINCES
    ):
        return "CONFIRMED_NL"

    # ---------------------------------------------------------
    # 4. Unknown.
    # ---------------------------------------------------------

    return "UNKNOWN"
