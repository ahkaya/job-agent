"""Almelo merkezli sehir-mesafe tablosu (km, kus ucusu yaklasik)."""

DISTANCE_MAP = {
    "almelo": 0,
    "hengelo": 15,
    "enschede": 23,
    "hardenberg": 23,
    "deventer": 34,
    "coevorden": 35,
    "raalte": 26,
    "hellendoorn": 14,
    "zwolle": 42,
    "hoogeveen": 43,
    "apeldoorn": 50,
    "kampen": 56,
    "steenwijk": 60,
    "emmen": 63,
    "arnhem": 66,
    "nijmegen": 79,
    "assen": 71,
    "lelystad": 82,
    "amersfoort": 90,
    "groningen": 96,
    "almere": 100,
    "utrecht": 109,
    "leeuwarden": 110,
    "s-hertogenbosch": 118,
    "den bosch": 118,
    "amsterdam": 120,
    "eindhoven": 130,
    "alkmaar": 134,
    "tilburg": 137,
    "haarlem": 138,
    "breda": 154,
    "rotterdam": 154,
    "den haag": 164,
    "the hague": 164,
    "delft": 163,
    "heerlen": 171,
    "maastricht": 181,
    "middelburg": 230,
    "enkhuizen": 130,
    "schijndel": 145,
    "oss": 130,
    "tilburg": 137,
    "breda": 154,
    "helmond": 145,
    "roermond": 175,
    "venlo": 155,
    "ede": 75,
    "wageningen": 85,
    "zeist": 105,
    "amstelveen": 125,
    "hoofddorp": 130,
    "zaandam": 130,
    "purmerend": 130,
    "hilversum": 110,
    "goes": 220,
    "vlissingen": 240,
    "terneuzen": 230,
    "dordrecht": 170,
    "gorinchem": 145,
    "tiel": 125,
    "veenendaal": 95,
    "barneveld": 80,
    "harderwijk": 65,
    "dronten": 75,
    "urk": 65,
    "emmeloord": 80,
    "sneek": 125,
    "drachten": 120,
    "heerenveen": 105,
    "staphorst": 45,
    "meppel": 50,
    "hoogenveen": 43,
    "winterswijk": 60,
    "doetinchem": 60,
    "zutphen": 45,
    "deventer": 34,
    "rijssen": 10,
    "borne": 15,
    "oldenzaal": 20,
    "losser": 22,
    "tubbergen": 12,
    "vriezenveen": 8,
    "westerhaar": 10,
    "nijverdal": 12,
}


def get_distance(location):
    """Konumdan Almelo'ya yaklasik mesafeyi km cinsinden dondurur.

    Bilinmeyen sehir icin None doner.
    """
    if not location:
        return None

    loc = str(location).lower().strip()

    # Tam eslesme
    if loc in DISTANCE_MAP:
        return DISTANCE_MAP[loc]

    # Kismi eslesme (ornek: "Amsterdam, Netherlands" -> "amsterdam")
    for city, dist in DISTANCE_MAP.items():
        if city in loc or loc in city:
            return dist

    return None


def format_distance(km):
    """Mesafeyi okunabilir string'e cevirir."""
    if km is None:
        return "?"
    if km == 0:
        return "0 km"
    return f"{km} km"
