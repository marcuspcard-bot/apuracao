import csv
import hashlib
import io
import json
import re

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import SecaoEsperada
from app.core.locks import lock_keys
from app.schemas.secoes_esperadas import CadastroSecoes, ConfirmarCadastro


def parse_sections_csv(content: bytes) -> CadastroSecoes:
    try:
        source = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("O arquivo deve ser um CSV em UTF-8.") from exc
    columns = ["zona", "secao_principal", "secoes_agregadas"]
    header = source.splitlines()[0] if source.splitlines() else ""
    delimiter = next(
        (
            d
            for d in (";", ",", "\t")
            if [c.strip().lower() for c in next(csv.reader([header], delimiter=d))] == columns
        ),
        None,
    )
    if delimiter is None:
        raise ValueError("Cabeçalho esperado: zona;secao_principal;secoes_agregadas.")
    groups = []
    try:
        reader = csv.reader(io.StringIO(source, newline=""), delimiter=delimiter, strict=True)
        next(reader)
        for row in reader:
            if not any(value.strip() for value in row):
                continue
            if len(row) != 3:
                raise ValueError(f"Linha {reader.line_num}: são esperadas três colunas.")
            zone, main, aggregated = (value.strip() for value in row)
            groups.append(
                {
                    "zona": zone,
                    "secao_principal": main,
                    "secoes_agregadas": re.split(r"[\s,]+", aggregated) if aggregated else [],
                }
            )
        return CadastroSecoes(grupos=groups)
    except csv.Error as exc:
        raise ValueError("CSV inválido. Confira as colunas e as aspas.") from exc
    except ValidationError as exc:
        messages = [e["msg"].removeprefix("Value error, ") for e in exc.errors()]
        raise ValueError("Lista de seções inválida: " + "; ".join(messages[:5])) from exc


def load_sections(db: Session, scope: dict) -> list[SecaoEsperada]:
    return list(db.scalars(select(SecaoEsperada).filter_by(**scope)).all())


def list_version(rows: list[SecaoEsperada]) -> str:
    content = sorted((s.zona, s.numero_secao, s.secao_principal) for s in rows)
    return hashlib.sha256(json.dumps(content).encode()).hexdigest()


def save_sections(db: Session, scope: dict, body: ConfirmarCadastro):
    with db.begin():
        lock_keys(db, ["expected-sections:" + json.dumps(scope, sort_keys=True, default=str)])
        current = load_sections(db, scope)
        if list_version(current) != body.versao_lista:
            raise HTTPException(409, "A lista mudou desde a prévia. Selecione o arquivo novamente.")
        db.execute(delete(SecaoEsperada).filter_by(**scope))
        for group in body.grupos:
            db.add_all(
                [
                    SecaoEsperada(
                        **scope,
                        zona=group.zona,
                        zona_chave=str(int(group.zona)),
                        numero_secao=number,
                        secao_chave=str(int(number)),
                        secao_principal=group.secao_principal,
                        principal_chave=str(int(group.secao_principal)),
                    )
                    for number in [group.secao_principal, *group.secoes_agregadas]
                ]
            )


def section_status(rows: list[SecaoEsperada], imported: list[dict]):
    coverage = {(int(s["zona"]), int(s["secao"])): s for s in imported}
    groups = {}
    pending = 0
    for expected in sorted(rows, key=lambda s: (int(s.zona_chave), int(s.secao_chave))):
        group = groups.setdefault(
            (expected.zona_chave, expected.principal_chave),
            {
                "zona": expected.zona,
                "secao_principal": expected.secao_principal,
                "principal": None,
                "agregadas": [],
            },
        )
        found = coverage.get((int(expected.zona_chave), int(expected.secao_chave)))
        item = {
            "numero": expected.numero_secao,
            "apurada": found is not None and not found.get("parcial", False),
            "parcial": bool(found and found.get("parcial", False)),
            "boletim_id": found["boletim_id"] if found else None,
            "secao_principal_bu": found["secao_principal"] if found else None,
            "vinculo_divergente": bool(
                found and int(found["secao_principal"]) != int(expected.principal_chave)
            ),
        }
        pending += not item["apurada"]
        if expected.secao_chave == expected.principal_chave:
            group["principal"] = item
        else:
            group["agregadas"].append(item)
    result = []
    for group in groups.values():
        members = [group["principal"], *group["agregadas"]]
        group["status"] = (
            "APURADA"
            if all(s["apurada"] for s in members)
            else "PARCIAL"
            if any(s["apurada"] or s["parcial"] for s in members)
            else "PENDENTE"
        )
        result.append(group)
    principals_expected = len(result) if rows else None
    # A registered principal counts only its own BU, not coverage as an aggregate.
    principals_counted = (
        sum(g["principal"]["apurada"] and not g["principal"]["vinculo_divergente"] for g in result)
        if rows
        else sum(s["tipo"] == "PRINCIPAL" and not s.get("parcial", False) for s in imported)
    )
    return {
        "lista_secoes_importada": bool(rows),
        "secoes_esperadas": len(rows) if rows else None,
        "secoes_pendentes": pending if rows else None,
        "secoes_principais_esperadas": principals_expected,
        "secoes_principais_apuradas": principals_counted,
        "secoes_principais_pendentes": (
            principals_expected - principals_counted if principals_expected is not None else None
        ),
        "grupos_secoes": sorted(result, key=lambda g: (int(g["zona"]), int(g["secao_principal"]))),
    }
