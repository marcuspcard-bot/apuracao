"""Synthetic election figures exclusively for parser and browser tests."""

import re

import pymupdf


OFFICES = [
    (
        "DEPUTADO FEDERAL",
        [("0123", "ANA CLÁUDIA", 10), ("5678", "BRUNO SILVA", 5)],
        (15, 2, 1, 3, 21),
    ),
    (
        "DEPUTADO ESTADUAL",
        [
            ("12345", "CARLOS SOUZA", 12),
            ("56789", "DÉBORA LIMA", 6),
            ("00001", "ÉRICA DOS SANTOS", 0),
        ],
        (18, 1, 1, 2, 22),
    ),
    ("DEPUTADO DISTRITAL", [("23456", "FÁBIO ALVES", 4)], (4, 3, 0, 1, 8)),
    ("SENADOR", [("123", "GUSTAVO ARAÚJO", 40), ("456", "HELENA COSTA", 30)], (70, 0, 3, 4, 77)),
    ("GOVERNADOR", [("12", "IGOR FERREIRA", 80), ("45", "JOANA DIAS", 70)], (150, 0, 2, 1, 153)),
    ("PRESIDENTE", [("13", "KÁTIA RIBEIRO", 90), ("22", "LUÍS MENDES", 80)], (170, 0, 4, 3, 177)),
]


def office_text(office) -> str:
    name, candidates, totals = office
    nominal, legend, blank, null, total = totals
    rows = "\n".join(f"{name}  {number}  {votes:04}" for number, name, votes in candidates)
    legend_line = f"Votos de legenda {legend:04}\n" if legend else ""
    return f"""---------------- {name} ----------------
Nome do candidato Num cand Votos
{rows}
Total de votos Nominais {nominal:04}
{legend_line}Brancos {blank:04}
Nulos {null:04}
Total Apurado {total:04}
"""


def document_text(reference: str, offices=None, section="0777") -> str:
    prefix = reference[: reference.index("-----------------------PRESIDENTE")]
    prefix = re.sub(r"(Seção Eleitoral\s+)\d+", lambda m: m[1] + section, prefix)
    prefix = re.sub(r"(Quantidade de seções agregadas\s+)\d+", lambda m: m[1] + "0000", prefix)
    prefix = re.sub(r"Seções Agregadas:[\d\s]+", "", prefix)
    suffix = reference[reference.index("ASSINATURA QR CODE") :]
    body = "\n".join(office_text(o) for o in (OFFICES if offices is None else offices))
    return prefix + body + "\n" + suffix


def render_pdf(text: str) -> bytes:
    with pymupdf.open() as doc:
        # Honor form-feed breaks and paginate long text without truncation.
        for part in text.split("\f"):
            lines = part.splitlines()
            for start in range(0, len(lines), 48):
                page = doc.new_page(width=700, height=850)
                page.insert_text((24, 25), "\n".join(lines[start : start + 48]), fontsize=10)
        return doc.tobytes()
