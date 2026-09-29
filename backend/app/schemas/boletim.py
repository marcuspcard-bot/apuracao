from datetime import date, time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

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
    preview_token: str = Field(min_length=80, max_length=75000000)
