"""Synthetic bulletins for the isolated database and browser tests only."""

import re

from tests.multicargo_fixture import document_text


def bacabal_text(reference: str, section="0001", aggregated=()) -> str:
    offices = [
        (
            "DEPUTADO FEDERAL",
            [("0123", "CANDIDATO FEDERAL TESTE", 10)],
            (10, 2, 0, 0, 12),
        ),
        (
            "GOVERNADOR",
            [("13", "CANDIDATO GOVERNADOR TESTE", 7)],
            (7, 0, 0, 0, 7),
        ),
        (
            "PRESIDENTE",
            [("13", "CANDIDATO PRESIDENTE TESTE", 30), ("22", "CANDIDATO SEM VOTOS", 0)],
            (30, 0, 0, 0, 30),
        ),
    ]
    text = document_text(reference, offices, section=section)
    text = text.replace("07/10/2018", "04/10/2026").replace(
        "Eleições Gerais 2018", "Eleições Gerais 2026"
    )
    text = text.replace("30848", "07234").replace("XANGAI", "BACABAL").replace("[ZZ]", "[MA]")
    text = re.sub(r"(Zona Eleitoral\s+)\d+", r"\g<1>0013", text)
    aggregate_header = f"Quantidade de seções agregadas {len(aggregated):04}"
    if aggregated:
        aggregate_header += "\nSeções Agregadas: " + " ".join(aggregated)
    text = re.sub(r"Quantidade de seções agregadas\s+\d+", aggregate_header, text)
    return "DOCUMENTO SINTETICO DE TESTE - SEM VALIDADE ELEITORAL\n" + text
