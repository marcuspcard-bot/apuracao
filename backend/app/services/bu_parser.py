import re
from dataclasses import dataclass

from pydantic import ValidationError

from app.schemas.boletim import BoletimDados, Cargo, ResultadoVaga
from app.services.bu_header import parse_header
from app.services.offices import (
    OFFICES_WITH_SEATS,
    normalize_office_name,
    normalize_seat_label,
    normalized,
)

TOTAL_LABELS = {
    "votos_nominais": r"(?:TOTAL\s+(?:DE\s+)?)?VOTOS\s+NOMINAIS",
    "votos_legenda": r"(?:TOTAL\s+(?:DE\s+)?)?VOTOS\s+(?:DE\s+)?LEGENDA",
    "brancos": r"(?:TOTAL\s+(?:DE\s+)?)?(?:VOTOS\s+)?BRANCOS",
    "nulos": r"(?:TOTAL\s+(?:DE\s+)?)?(?:VOTOS\s+)?NULOS",
    "total_apurado": r"TOTAL\s+APURADO",
}
TOTAL_START = re.compile(
    r"(?m)^\s*(?:" + "|".join(TOTAL_LABELS.values()) + r"|ELEITORES\s+APTOS)\b"
)
TABLE_HEADER = re.compile(
    r"^(?:NOME DO CANDIDATO(?: NUM(?:ERO)?\.? CAND(?:IDATO)?\.? VOTOS)?|NUM(?:ERO)?\.? CAND(?:IDATO)?\.?(?: VOTOS)?|VOTOS)$"
)
PAGE_NOISE = re.compile(
    r"^(?:\(VIA DIGITAL\)|JUSTICA ELEITORAL|TRIBUNAL REGIONAL ELEITORAL.*|BOLETIM DE URNA|ELEICOES .+|ELEICAO .+|[12][º°]? TURNO|\(\d{2}/\d{2}/\d{4}\)|CODIGO VERIFICADOR:.*|PAGINA \d+(?: (?:DE|/) \d+)?|\d+\s*/\s*\d+)$"
)
FOOTER_START = re.compile(r"^\s*(?:ASSINATURA QR CODE|CODIGO DE IDENTIFICACAO DA CARGA)\b")


@dataclass
class OfficeBlock:
    nome: str
    text: str


def office_heading(line: str) -> tuple[str, str | None] | None:
    name = normalize_office_name(line)
    if name:
        return name, None
    clean = " ".join(normalized(line).strip(" -=_–—").split())
    for office in OFFICES_WITH_SEATS:
        if clean.startswith(office):
            seat = normalize_seat_label(clean[len(office) :])
            if seat:
                return office, seat
    return None


def detect_office_blocks(text: str) -> list[OfficeBlock]:
    lines = text.replace("\r\n", "\n").replace("\f", "\n").splitlines()
    first = next(
        (
            i
            for i, line in enumerate(lines)
            if office_heading(line)
            or (i + 1 < len(lines) and office_heading(line + " " + lines[i + 1]))
        ),
        None,
    )
    if first is not None:
        preamble = "\n".join(lines[:first]).strip()
        if re.search(r"NOME\s+DO\s+CANDIDATO", normalized(preamble)):
            raise ValueError(
                "Falha no parser: tabela sem cargo reconhecido antes do primeiro bloco."
            )
        if preamble and len(preamble) > 80:
            # Remove complete repeated document headers, never isolated numeric values.
            pattern = r"\s+".join(re.escape(token) for token in preamble.split())
            text = re.sub(pattern, "", "\n".join(lines), flags=re.IGNORECASE)
            lines = text.splitlines()
    blocks: list[OfficeBlock] = []
    current_name = None
    current_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        heading = office_heading(line)
        # Office titles themselves may wrap across lines.
        if not heading and i + 1 < len(lines):
            heading = office_heading(line + " " + lines[i + 1])
            if heading:
                i += 1
        if heading:
            name, seat = heading
            if current_name and name != current_name:
                blocks.append(OfficeBlock(current_name, "\n".join(current_lines)))
                current_lines = []
            current_name = name
            if seat:
                current_lines.append(seat)
        elif FOOTER_START.match(normalized(line)):
            break
        else:
            clean = " ".join(normalized(line).split())
            if re.fullmatch(r"[-=–—_]{2,}\s*[A-Z][A-Z ]+\s*[-=–—_]{2,}", clean):
                raise ValueError(f"Falha no parser: cargo não reconhecido: {line.strip(' -=_')}.")
            if not current_name and clean.startswith("NOME DO CANDIDATO"):
                raise ValueError("Falha no parser: tabela sem cargo reconhecido.")
            if current_name:
                current_lines.append(line)
        i += 1
    if current_name:
        blocks.append(OfficeBlock(current_name, "\n".join(current_lines)))
    if not blocks:
        raise ValueError("Falha no parser: nenhum cargo reconhecido no documento.")
    return blocks


def clean_office_text(text: str) -> str:
    text = re.sub(
        r"NOME\s+DO\s+CANDIDATO(?:\s+N[ÚU]M(?:ERO)?\.?\s+CAND(?:IDATO)?\.?\s+VOTOS)?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    lines = []
    for line in text.splitlines():
        value = " ".join(normalized(line).split())
        if not value or re.fullmatch(r"[-=_–—]+", value):
            continue
        if TABLE_HEADER.fullmatch(value) or PAGE_NOISE.fullmatch(value):
            continue
        lines.append(line.strip())
    return "\n".join(lines)


def parse_candidates(text: str, office_name: str) -> list[dict]:
    boundary = TOTAL_START.search(normalized(text))
    candidate_text = text[: boundary.start()] if boundary else text
    return parse_vote_rows(candidate_text, office_name, "candidatos")


def parse_vote_rows(text: str, office_name: str, kind: str) -> list[dict]:
    pattern = r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿªº\s.'’()/+−-]*?)\s+(\d{1,20})\s+(\d+)(?=\s|$)"
    rows = re.findall(pattern, text)
    if re.sub(pattern, "", text).strip():
        raise ValueError(f"Falha no parser: linhas de {kind} não reconhecidas em {office_name}.")
    return [
        {"nome": " ".join(name.split()), "numero": number, "votos": int(votes)}
        for name, number, votes in rows
    ]


def extract_legend_tables(text: str, office_name: str) -> tuple[str, list[dict]]:
    lines = text.splitlines()
    remaining, parties = [], []
    i = 0
    heading = re.compile(TOTAL_LABELS["votos_legenda"] + r"\s*:?")
    while i < len(lines):
        line = lines[i]
        if heading.fullmatch(normalized(line)):
            end = i + 1
            while end < len(lines) and not TOTAL_START.match(normalized(lines[end])):
                end += 1
            table = "\n".join(lines[i + 1 : end])
            # A number on the following line is a total, not a party table.
            if table and re.match(r"[A-Za-zÀ-ÿ]", table):
                parties.extend(parse_vote_rows(table, office_name, "legenda"))
                i = end
                continue
        remaining.append(line)
        i += 1
    return "\n".join(remaining), parties


def parse_office_totals(text: str, office_name: str) -> tuple[dict, list[str]]:
    source = normalized(text)
    values, problems = {}, []
    for field, label in TOTAL_LABELS.items():
        matches = re.findall(rf"(?m)^\s*{label}\s*:?\s*(\d+)[ \t]*(?=\n|$)", source)
        occurrences = re.findall(rf"(?m)^\s*{label}\b", source)
        present = bool(occurrences)
        if not matches:
            if field == "votos_legenda" and not present:
                values[field] = 0
            else:
                values[field] = None
                problems.append(
                    f"Não foi possível identificar {field.replace('_', ' ')} do cargo {office_name}."
                )
        elif len(matches) != len(occurrences) or len(set(int(v) for v in matches)) > 1:
            values[field] = None
            problems.append(
                f"Valores conflitantes para {field.replace('_', ' ')} do cargo {office_name}."
            )
        else:
            values[field] = int(matches[0])
    boundary = TOTAL_START.search(source)
    if boundary:
        tail = source[boundary.start() :]
        for label in [
            *TOTAL_LABELS.values(),
            r"ELEITORES\s+APTOS",
            r"ORIGINAIS DA SECAO",
            r"TEMPORARIOS NA SECAO",
        ]:
            tail = re.sub(rf"(?m)^\s*{label}\s*:?\s*\d+[ \t]*(?=\n|$)", "", tail)
        if tail.strip():
            problems.append(
                f"Conteúdo não reconhecido na área de totais do cargo {office_name}: {tail.strip()[:120]}."
            )
    return values, problems


def extract_party_blocks(text: str, office_name: str) -> tuple[str, list[str], int | None]:
    """Separate party subtotals from the office's authoritative totals."""
    heading = re.compile(r"(?m)^[ \t]*PARTIDO\s*:\s*(\d+)\s*-\s*[^\n]+$", re.IGNORECASE)
    matches = list(heading.finditer(normalized(text)))
    if not matches:
        return text, [], None
    remaining = [text[: matches[0].start()]]
    problems, numbers = [], []
    legend_sum = 0
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        boundary = re.search(r"(?m)^\s*ELEITORES\s+APTOS\b", normalized(body))
        tail = body[boundary.start() :] if boundary else ""
        body = body[: boundary.start()] if boundary else body
        source = normalized(body)
        label = TOTAL_LABELS["votos_legenda"]
        legend = re.findall(rf"(?m)^\s*{label}\s*:?\s*(\d+)[ \t]*(?=\n|$)", source)
        total = re.findall(r"(?m)^\s*TOTAL DO PARTIDO\s*:?\s*(\d+)[ \t]*(?=\n|$)", source)
        if len(legend) != 1 or len(total) != 1:
            raise ValueError(
                f"Falha no parser: subtotais do partido {match[1]} inválidos em {office_name}."
            )
        rows = re.sub(rf"(?m)^\s*{label}\s*:?\s*\d+[ \t]*(?=\n|$)", "", body, flags=re.IGNORECASE)
        rows = re.sub(r"(?mi)^\s*Total do partido\s*:?\s*\d+[ \t]*(?=\n|$)", "", rows)
        rows = "\n".join(
            line
            for line in rows.splitlines()
            if normalized(line).strip() != "NAO HA VOTOS NOMINAIS"
        )
        candidates = parse_vote_rows(rows, office_name, "candidatos")
        if sum(c["votos"] for c in candidates) + int(legend[0]) != int(total[0]):
            problems.append(
                f"{office_name}: total do partido {match[1]} difere de nominais + legenda."
            )
        numbers.append(str(int(match[1])))
        legend_sum += int(legend[0])
        remaining.extend([rows, tail])
    if len(numbers) != len(set(numbers)):
        problems.append(f"{office_name}: há números de partido repetidos.")
    return "\n".join(remaining), problems, legend_sum


def parse_result(text: str, name: str) -> dict:
    clean = clean_office_text(text)
    clean, party_problems, party_legend = extract_party_blocks(clean, name)
    clean, parties = extract_legend_tables(clean, name)
    values, problems = parse_office_totals(clean, name)
    problems.extend(party_problems)
    if party_legend is not None and values["votos_legenda"] != party_legend:
        problems.append(f"{name}: soma dos votos dos partidos difere dos votos de legenda.")
    if parties:
        label = TOTAL_LABELS["votos_legenda"]
        if not re.search(rf"(?m)^\s*{label}\b", normalized(clean)):
            values["votos_legenda"] = None
            problems.append(f"Não foi possível identificar votos legenda do cargo {name}.")
        elif (
            values["votos_legenda"] is not None
            and sum(p["votos"] for p in parties) != values["votos_legenda"]
        ):
            problems.append(f"{name}: soma dos votos dos partidos difere dos votos de legenda.")
        numbers = [str(int(p["numero"])) for p in parties]
        if len(numbers) != len(set(numbers)):
            problems.append(f"{name}: há números de partido repetidos na tabela de legenda.")
    return {"candidatos": parse_candidates(clean, name), **values, "problemas": problems}


def parse_office_block(block: OfficeBlock) -> Cargo:
    if block.nome not in OFFICES_WITH_SEATS:
        return Cargo(nome=block.nome, **parse_result(block.text, block.nome))
    parts: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in block.text.splitlines():
        seat = normalize_seat_label(line)
        if seat:
            if parts[-1][0] != seat:
                parts.append((seat, []))
        else:
            parts[-1][1].append(line)
    if len(parts) == 1:
        return Cargo(nome=block.nome, **parse_result(block.text, block.nome))
    # Seat-only documents have no overall totals: retain nulls rather than deriving them.
    prefix = clean_office_text("\n".join(parts[0][1]))
    overall = (
        parse_result(prefix, block.nome)
        if prefix
        else {
            "candidatos": [],
            "votos_nominais": None,
            "votos_legenda": 0,
            "brancos": None,
            "nulos": None,
            "total_apurado": None,
            "problemas": [],
        }
    )
    seats = [
        ResultadoVaga(
            identificacao=seat, **parse_result("\n".join(lines), f"{block.nome} / {seat}")
        )
        for seat, lines in parts[1:]
    ]
    return Cargo(nome=block.nome, vagas=seats, **overall)


def parse_bu_text(text: str) -> BoletimDados:
    try:
        data = parse_header(text)
        blocks = detect_office_blocks(text)
        data["cargos"] = [parse_office_block(block) for block in blocks]
        return BoletimDados.model_validate(data)
    except (ValidationError, OverflowError) as exc:
        raise ValueError("Falha no parser: campos ausentes ou fora do formato esperado.") from exc
