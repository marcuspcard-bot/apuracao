"""Reports of complete bulletins, with each aggregated group counted once."""

import csv
from collections import defaultdict
from io import StringIO

from sqlalchemy import select

from app.models import CandidatoVoto, Resultado
from app.services.acompanhamento import _load_bulletins, _load_covered_sections
from app.services.candidate_identity import candidate_key


def report_data(db, election_date):
    bulletins = {b.id: b for b in _load_bulletins(db, election_date) if b.origem != "MANUAL"}
    if not bulletins:
        return {"cargos": [], "linhas": []}
    rows = db.execute(
        select(Resultado.boletim_id, Resultado.cargo, CandidatoVoto)
        .join(CandidatoVoto, CandidatoVoto.resultado_id == Resultado.id)
        .where(Resultado.boletim_id.in_(bulletins))
    )
    candidates = defaultdict(dict)
    grouped = defaultdict(list)
    for bulletin_id, office, candidate in rows:
        key = candidate_key(candidate.numero_candidato)
        candidates[office].setdefault(
            key,
            {
                "numero": key,
                "nome": candidate.nome_candidato,
            },
        )
        grouped[bulletin_id, office, key].append(candidate)
    votes = defaultdict(lambda: defaultdict(dict))
    for (bulletin_id, office, key), entries in grouped.items():
        overall = [c for c in entries if c.vaga == ""]
        votes[bulletin_id][office][key] = sum(c.votos for c in (overall or entries))
    offices = defaultdict(set)
    for bulletin_id, office in db.execute(
        select(Resultado.boletim_id, Resultado.cargo).where(Resultado.boletim_id.in_(bulletins))
    ):
        offices[bulletin_id].add(office)
    aggregated = defaultdict(list)
    for section in _load_covered_sections(db, bulletins):
        if section["tipo"] == "AGREGADA":
            aggregated[section["boletim_id"]].append(section["secao"])
    return {
        "cargos": [
            {"nome": office, "candidatos": sorted(items.values(), key=lambda c: int(c["numero"]))}
            for office, items in sorted(candidates.items())
        ],
        "linhas": [
            {
                "zona": b.zona,
                "secao": b.secao,
                "agregadas": aggregated[str(b.id)],
                "cargos": {office: votes[b.id][office] for office in sorted(offices[b.id])},
            }
            for b in sorted(bulletins.values(), key=lambda b: (int(b.zona), int(b.secao)))
        ],
    }


def csv_report(data, office, numbers):
    return csv_report_selected(data, [{"cargo": office, "numero": n} for n in numbers])


def csv_report_selected(data, selections):
    available = {
        (office["nome"], candidate["numero"]): candidate
        for office in data["cargos"]
        for candidate in office["candidatos"]
    }
    keys = list(dict.fromkeys((s["cargo"], candidate_key(s["numero"])) for s in selections))
    if not keys or any(key not in available for key in keys):
        raise ValueError("Selecione candidatos disponíveis para o cargo e a eleição.")
    output = StringIO(newline="")
    writer = csv.writer(output, delimiter=";")

    def safe(value):
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value

    writer.writerow(
        [
            "Zona",
            "Seção principal",
            "Seções agregadas",
            *[
                safe(f"{office} — {available[office, number]['nome']} — {number}")
                for office, number in keys
            ],
        ]
    )
    for row in data["linhas"]:
        if any(office in row["cargos"] for office, _ in keys):
            writer.writerow(
                [
                    row["zona"],
                    row["secao"],
                    ", ".join(row["agregadas"]),
                    *[
                        row["cargos"][office].get(number, 0) if office in row["cargos"] else ""
                        for office, number in keys
                    ],
                ]
            )
    return output.getvalue().encode("utf-8-sig")
