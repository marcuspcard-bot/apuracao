from app.schemas.boletim import BoletimDados, ResultadoDados


def validate_result(result: ResultadoDados, name: str) -> list[str]:
    problems = list(result.problemas)
    fields = ("votos_nominais", "votos_legenda", "brancos", "nulos", "total_apurado")
    for field in fields:
        if getattr(result, field) is None and not any(
            field.replace("_", " ") in p for p in problems
        ):
            problems.append(
                f"Não foi possível identificar {field.replace('_', ' ')} do cargo {name}."
            )
    if all(getattr(result, field) is not None for field in fields):
        if (
            result.total_apurado
            != result.votos_nominais + result.votos_legenda + result.brancos + result.nulos
        ):
            problems.append(
                f"{name}: total apurado difere de nominais + legenda + brancos + nulos."
            )
    if (
        result.votos_nominais is not None
        and sum(v.votos for v in result.candidatos) != result.votos_nominais
    ):
        problems.append(f"{name}: soma dos votos dos candidatos difere dos votos nominais.")
    numbers = [str(int(v.numero)) for v in result.candidatos]
    if len(numbers) != len(set(numbers)):
        problems.append(f"{name}: há números de candidato repetidos.")
    return problems


def validate_bu(data: BoletimDados) -> list[str]:
    problems = []
    e = data.eleitores
    if e.aptos < e.comparecimento:
        problems.append("O comparecimento é maior que o número de eleitores aptos.")
    if e.faltosos != e.aptos - e.comparecimento:
        problems.append("Faltosos deve ser igual a aptos menos comparecimento.")
    if len(data.secoes_agregadas) != data.quantidade_secoes_agregadas:
        problems.append(
            "Quantidade de seções agregadas informada no boletim não corresponde à quantidade identificada."
        )
    sections = [str(int(s)) for s in [data.secao, *data.secoes_agregadas]]
    if len(set(sections)) != len(sections):
        problems.append("Há seções repetidas no boletim.")
    names = [c.nome for c in data.cargos]
    if len(set(names)) != len(names):
        problems.append("Há cargos repetidos no boletim.")
    for c in data.cargos:
        has_overall = bool(c.candidatos or c.problemas) or any(
            getattr(c, f) is not None
            for f in ("votos_nominais", "brancos", "nulos", "total_apurado")
        )
        if not c.vagas or has_overall:
            problems.extend(validate_result(c, c.nome))
        labels = [v.identificacao for v in c.vagas]
        if len(labels) != len(set(labels)):
            problems.append(f"{c.nome}: há vagas repetidas no boletim.")
        for vaga in c.vagas:
            problems.extend(validate_result(vaga, f"{c.nome} / {vaga.identificacao}"))
    return problems
