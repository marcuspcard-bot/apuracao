from datetime import date, time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator
from uuid import UUID

Code = Annotated[str, Field(pattern=r"^\d{1,20}$")]
Count = Annotated[int, Field(ge=0, le=10000000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Eleicao(StrictModel):
    descricao: str = Field(min_length=1, max_length=200)
    turno: Literal[1, 2]
    data: date


class Municipio(StrictModel):
    codigo: Code
    nome: str = Field(min_length=1, max_length=200)


class Eleitores(StrictModel):
    aptos: Count
    comparecimento: Count
    faltosos: Count


class Urna(StrictModel):
    codigo_identificacao: Code
    data_abertura: date
    hora_abertura: time
    data_fechamento: date
    hora_fechamento: time


class Candidato(StrictModel):
    numero: Code
    nome: str = Field(min_length=1, max_length=200)
    votos: Count


class ResultadoDados(StrictModel):
    candidatos: list[Candidato] = Field(max_length=10000)
    votos_nominais: Count | None
    votos_legenda: Count | None = 0
    brancos: Count | None
    nulos: Count | None
    total_apurado: Count | None
    problemas: list[str] = Field(default_factory=list)


class ResultadoVaga(ResultadoDados):
    identificacao: str = Field(min_length=1, max_length=100)


class Cargo(ResultadoDados):
    nome: str = Field(min_length=1, max_length=100)
    vagas: list[ResultadoVaga] = Field(default_factory=list, max_length=20)


class BoletimDados(StrictModel):
    eleicao: Eleicao
    municipio: Municipio
    zona: Code
    local_votacao: Code
    secao: Code
    quantidade_secoes_agregadas: Count
    secoes_agregadas: list[Code] = Field(max_length=1000)
    eleitores: Eleitores
    urna: Urna
    cargos: list[Cargo] = Field(min_length=1, max_length=30)
    assinatura_qrcode: str = Field(min_length=1, max_length=10000)
    codigo_carga: str = Field(pattern=r"^[\d.]{1,100}$")

    @computed_field
    @property
    def total_secoes_representadas(self) -> int:
        return 1 + self.quantidade_secoes_agregadas


class Confirmar(StrictModel):
    substituir_id: UUID | None = None
    preview_token: str = Field(min_length=80, max_length=75000000)


class CandidatoManual(Candidato):
    cargo: str = Field(min_length=1, max_length=100)


class BoletimManual(StrictModel):
    eleicao: Eleicao
    municipio: Municipio
    zona: Code
    secao: Code
    secoes_agregadas: list[Code] = Field(default_factory=list, max_length=1000)
    candidatos: list[CandidatoManual] = Field(min_length=1, max_length=200)
    foto_token: str | None = Field(default=None, min_length=80, max_length=75000000)

    @model_validator(mode="after")
    def validate_entries(self):
        from app.services.offices import normalize_office_name

        keys = set()
        for c in self.candidatos:
            office = normalize_office_name(c.cargo)
            if not office:
                raise ValueError("Cargo inválido.")
            c.cargo = office
            c.nome = c.nome.strip()
            key = (office, str(int(c.numero)))
            if not c.nome or key in keys:
                raise ValueError("Nome vazio ou candidato repetido no mesmo cargo.")
            keys.add(key)
        sections = [int(self.secao), *map(int, self.secoes_agregadas)]
        if len(sections) != len(set(sections)):
            raise ValueError("Seção repetida.")
        return self


class LerFotos(StrictModel):
    foto_token: str = Field(min_length=80, max_length=75000000)
