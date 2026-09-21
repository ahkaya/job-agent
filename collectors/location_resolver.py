import re
import unicodedata


# Dutch municipalities / commonly used Dutch city names.
# The list intentionally includes commonly encountered job-location names.
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
    "bergen op zoom",
    "beverwijk",
    "boxtel",
    "breda",
    "capelle aan den ijssel",
    "delft",
    "den bosch",
    "deventer",
    "doetinchem",
    "dordrecht",
    "eindhoven",
    "emmen",
    "enkhuizen",
    "enschede",
    "geleen",
    "goes",
    "gouda",
    "groningen",
    "haarlem",
    "harderwijk",
    "heerhugowaard",
    "heerlen",
    "helmond",
    "hengelo",
    "hilversum",
    "hoofddorp",
    "hoorn",
    "huizen",
    "kampen",
    "kerkrade",
    "leeuwarden",
    "leiden",
    "lelystad",
    "maastricht",
    "meppel",
    "middelburg",
    "nieuwegein",
    "nijmegen",
    "oosterhout",
    "oss",
    "purmerend",
    "roermond",
    "roosendaal",
    "rotterdam",
    "s hertogenbosch",
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


REMOTE_TERMS = {
    "remote",
    "fully remote",
    "work from anywhere",
    "work anywhere",
    "anywhere",
}


def normalize(text):
    text = unicodedata.normalize(
        "NFKC",
        str(text or ""),
    ).lower()

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
        Explicit Dutch country, province, or city signal.

    NOT_NL:
        Remote, empty, or no Dutch location signal.

    The collector intentionally does not attempt to identify every
    foreign city or country. For this job search, absence of a
    reliable Dutch location signal is sufficient to exclude the job.
    """

    text = normalize(location)

    # Remote jobs are always excluded.
    if any(
        contains_term(text, term)
        for term in REMOTE_TERMS
    ):
        return "NOT_NL"

    # Empty / placeholder locations are excluded.
    if not text or text in {"n a", "na", "location", "tbd"}:
        return "NOT_NL"

    # Explicit Netherlands signal.
    if any(
        contains_term(text, country)
        for country in NL_COUNTRY_TERMS
    ):
        return "CONFIRMED_NL"

    # Dutch city / municipality signal.
    if any(
        contains_term(text, city)
        for city in NL_CITIES
    ):
        return "CONFIRMED_NL"

    # Dutch province signal.
    if any(
        contains_term(text, province)
        for province in NL_PROVINCES
    ):
        return "CONFIRMED_NL"

    # Everything else is outside the target scope.
    return "NOT_NL"
