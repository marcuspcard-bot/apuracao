import re
from datetime import datetime

from app.services.offices import normalized


def capture(pattern: str, label: str, text: str, flags=re.MULTILINE) -> str:
    match = re.search(pattern, text, flags)
    if not match:
        raise ValueError(f"Falha no parser: não foi possível identificar {label}.")
    return match.group(1).strip()


def parse_aggregated_sections(source: str) -> tuple[int, list[str]]:
    source = normalized(source)
    principal = re.findall(r"SECAO\s+ELEITORAL\s*:?\s*(\d+)", source)
    if len({str(int(s)) for s in principal}) != 1:
        raise ValueError("Falha no parser: não foi possível identificar uma única seção principal.")
    count_label = r"QUANTIDADE\s+DE\s+SECOES\s+AGREGADAS"
    counts = re.findall(rf"{count_label}\s*:?\s*(\d+)[ \t]*(?=\n|$)", source)
    has_count = re.search(count_label, source) is not None
    if has_count and (not counts or len(set(map(int, counts))) != 1):
        raise ValueError("Falha no parser: quantidade de seções agregadas inválida ou conflitante.")
    label = re.search(r"(?m)^[ \t]*SECOES[ \t]+AGREGADAS\b[ \t]*:?[ \t]*(.*)$", source)
    sections = []
    if label:
        lines = [label[1], *source[label.end() :].splitlines()]
        for line in lines:
            value = line.strip()
            if not value:
                continue
            if re.fullmatch(r"[\d \t]+", value):
                sections.extend(value.split())
            else:
                if re.match(r"\d", value) or (line == label[1] and value):
                    raise ValueError("Falha no parser: lista de seções agregadas ilegível.")
                break
    if not has_count:
        if label:
            raise ValueError("Falha no parser: lista de seções agregadas sem quantidade informada.")
        return 0, []
    # Preserve the observed list even when the stated count is zero; validation detects conflicts.
    return int(counts[0]), sections


def parse_urn_identifier(source: str) -> str:
    labels = r"(?:CODIGO (?:DE )?IDENTIFICACAO UE|URNA EFETIVADA)"
    matches = re.findall(rf"{labels}\s*:?\s*(\d+)", source)
    if not matches:
        raise ValueError("Falha no parser: não foi possível identificar a identificação da urna.")
    if len({str(int(value)) for value in matches}) != 1:
        raise ValueError("Falha no parser: identificações da urna conflitantes.")
    return matches[0]


def parse_header(text: str) -> dict:
    original = re.sub(r"[^\S\n]+", " ", text).strip()
    source = normalized(original)

    def field(pattern, label):
        return capture(pattern, label, source)

    def number(label):
        return field(rf"{label}\s*:?\s*(\d+)", label.lower())

    def date_value(value):
        try:
            return datetime.strptime(value, "%d/%m/%Y").date()
        except ValueError as exc:
            raise ValueError("Falha no parser: data inválida no boletim.") from exc

    def date_field(label):
        return date_value(field(rf"{label}\s*:?\s*(\d{{2}}/\d{{2}}/\d{{4}})", label.lower()))

    count, sections = parse_aggregated_sections(source)
    signature = field(
        r"ASSINATURA QR CODE\s*:\s*((?:[ \t]*[A-F0-9]+[ \t]*(?:\n|$))+)", "assinatura QR Code"
    )
    return {
        "eleicao": {
            "descricao": capture(r"(Elei[çc][õo]es[^\n]+)", "eleição", original, re.IGNORECASE),
            "turno": int(field(r"([12])\s*[º°O]?\s*TURNO", "turno")),
            "data": date_value(field(r"\((\d{2}/\d{2}/\d{4})\)", "data da eleição")),
        },
        "municipio": {
            "codigo": number("MUNICIPIO"),
            "nome": capture(
                r"Munic[íi]pio\s*:?\s*\d+\s+([^\n]+)", "município", original, re.IGNORECASE
            ),
        },
        "zona": number("ZONA ELEITORAL"),
        "local_votacao": number("LOCAL DE VOTACAO"),
        "secao": number("SECAO ELEITORAL"),
        "quantidade_secoes_agregadas": count,
        "secoes_agregadas": sections,
        "eleitores": {
            "aptos": int(number("ELEITORES APTOS")),
            "comparecimento": int(number("COMPARECIMENTO")),
            "faltosos": int(number("ELEITORES FALTOSOS")),
        },
        "urna": {
            "codigo_identificacao": parse_urn_identifier(source),
            "data_abertura": date_field("DATA DE ABERTURA DA UE"),
            "hora_abertura": field(
                r"HORARIO DE ABERTURA\s*(\d{2}:\d{2}:\d{2})", "hora de abertura"
            ),
            "data_fechamento": date_field("DATA DE FECHAMENTO DA UE"),
            "hora_fechamento": field(
                r"HORARIO DE FECHAMENTO\s*(\d{2}:\d{2}:\d{2})", "hora de fechamento"
            ),
        },
        "assinatura_qrcode": re.sub(r"\s", "", signature),
        "codigo_carga": field(r"CODIGO DE IDENTIFICACAO DA CARGA\s*([\d.]+)", "código da carga"),
    }
