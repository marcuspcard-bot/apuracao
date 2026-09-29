import re
import unicodedata

# Extend this list without changing candidate parsing or candidate-number lengths.
RECOGNIZED_OFFICES = (
    "DEPUTADO FEDERAL",
    "DEPUTADO ESTADUAL",
    "DEPUTADO DISTRITAL",
    "SENADOR",
    "GOVERNADOR",
    "PRESIDENTE",
)
OFFICES_WITH_SEATS = frozenset({"SENADOR"})


def normalized(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)
    ).upper()


def normalize_office_name(value: str) -> str | None:
    name = " ".join(normalized(value).strip(" -=_–—\t\n").split())
    return name if name in RECOGNIZED_OFFICES else None


def normalize_seat_label(value: str) -> str | None:
    label = " ".join(normalized(value).strip(" -=_–—():\t\n").split())
    if re.fullmatch(r"(?:\d+\s*[ºª°OA]?|PRIMEIRA|SEGUNDA|TERCEIRA)\s+VAGA|VAGA\s+\d+", label):
        return label
    return None
