from app.models import Boletim, BoletimSecao, CandidatoVoto, Resultado
from app.schemas.boletim import BoletimDados
from app.services.duplicate_checker import scope


def make_boletim(
    data: BoletimDados, filename: str, file_hash: str, bucket: str, path: str
) -> Boletim:
    b = Boletim(
        eleicao_descricao=data.eleicao.descricao,
        eleicao_turno=data.eleicao.turno,
        eleicao_data=data.eleicao.data,
        municipio_codigo=data.municipio.codigo,
        municipio_nome=data.municipio.nome,
        zona=data.zona,
        local_votacao=data.local_votacao,
        secao=data.secao,
        quantidade_secoes_agregadas=data.quantidade_secoes_agregadas,
        eleitores_aptos=data.eleitores.aptos,
        comparecimento=data.eleitores.comparecimento,
        faltosos=data.eleitores.faltosos,
        codigo_urna=data.urna.codigo_identificacao,
        data_abertura=data.urna.data_abertura,
        hora_abertura=data.urna.hora_abertura,
        data_fechamento=data.urna.data_fechamento,
        hora_fechamento=data.urna.hora_fechamento,
        assinatura_qrcode=data.assinatura_qrcode,
        codigo_carga=data.codigo_carga,
        arquivo_nome_original=filename,
        arquivo_hash=file_hash,
        storage_bucket=bucket,
        storage_path=path,
    )
    b.secoes = [
        BoletimSecao(
            numero_secao=n,
            secao_chave=str(int(n)),
            tipo="PRINCIPAL" if i == 0 else "AGREGADA",
            **scope(data),
        )
        for i, n in enumerate([data.secao, *data.secoes_agregadas])
    ]
    b.resultados = [
        Resultado(
            cargo=c.nome,
            votos_nominais=c.votos_nominais,
            votos_legenda=c.votos_legenda,
            brancos=c.brancos,
            nulos=c.nulos,
            total_apurado=c.total_apurado,
            vagas=[v.model_dump(mode="json", exclude={"candidatos", "problemas"}) for v in c.vagas],
            candidatos=[
                CandidatoVoto(
                    numero_candidato=v.numero, nome_candidato=v.nome, votos=v.votos, vaga=label
                )
                for label, candidates in [
                    ("", c.candidatos),
                    *[(seat.identificacao, seat.candidatos) for seat in c.vagas],
                ]
                for v in candidates
            ],
        )
        for c in data.cargos
    ]
    return b


def detail(b: Boletim):
    response = {
        "id": b.id,
        "created_at": b.created_at,
        "arquivo_nome_original": b.arquivo_nome_original,
        "arquivo_hash": b.arquivo_hash,
        "storage_bucket": b.storage_bucket,
        "storage_path": b.storage_path,
        "secoes": [{"numero_secao": s.numero_secao, "tipo": s.tipo} for s in b.secoes],
        "dados": {
            "eleicao": {
                "descricao": b.eleicao_descricao,
                "turno": b.eleicao_turno,
                "data": b.eleicao_data,
            },
            "municipio": {"codigo": b.municipio_codigo, "nome": b.municipio_nome},
            "zona": b.zona,
            "local_votacao": b.local_votacao,
            "secao": b.secao,
            "quantidade_secoes_agregadas": b.quantidade_secoes_agregadas,
            "total_secoes_representadas": b.total_secoes_representadas,
            "secoes_agregadas": sorted(s.numero_secao for s in b.secoes if s.tipo == "AGREGADA"),
            "eleitores": {
                "aptos": b.eleitores_aptos,
                "comparecimento": b.comparecimento,
                "faltosos": b.faltosos,
            },
            "urna": {
                "codigo_identificacao": b.codigo_urna,
                "data_abertura": b.data_abertura,
                "hora_abertura": b.hora_abertura,
                "data_fechamento": b.data_fechamento,
                "hora_fechamento": b.hora_fechamento,
            },
            "cargos": [
                {
                    "nome": r.cargo,
                    "votos_nominais": r.votos_nominais,
                    "votos_legenda": r.votos_legenda,
                    "brancos": r.brancos,
                    "nulos": r.nulos,
                    "total_apurado": r.total_apurado,
                    "candidatos": [
                        {"numero": c.numero_candidato, "nome": c.nome_candidato, "votos": c.votos}
                        for c in sorted(r.candidatos, key=lambda c: c.numero_candidato)
                        if not c.vaga
                    ],
                    "vagas": [
                        {
                            **seat,
                            "candidatos": [
                                {
                                    "numero": c.numero_candidato,
                                    "nome": c.nome_candidato,
                                    "votos": c.votos,
                                }
                                for c in sorted(r.candidatos, key=lambda c: c.numero_candidato)
                                if c.vaga == seat["identificacao"]
                            ],
                        }
                        for seat in r.vagas
                    ],
                }
                for r in b.resultados
            ],
            "assinatura_qrcode": b.assinatura_qrcode,
            "codigo_carga": b.codigo_carga,
        },
    }
    # Preserve existing consumers of dados while exposing the requested detail contract.
    response["cargos"] = response["dados"]["cargos"]
    response["dados_gerais"] = {k: v for k, v in response["dados"].items() if k != "cargos"}
    return response
