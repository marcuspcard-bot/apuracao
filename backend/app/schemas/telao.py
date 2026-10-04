from datetime import date, datetime
from uuid import UUID

from pydantic import Field, StrictBool, field_validator, model_validator

from app.schemas.boletim import Code, StrictModel
from app.services.candidate_identity import candidate_key
from app.services.offices import normalize_office_name


class TelaoSelection(StrictModel):
    cargo: str = Field(max_length=100)
    numero: Code
    ativo: StrictBool = True
    # Omitted preserves the photo; null removes it; a data URL replaces it.
    foto: str | None = Field(default=None, max_length=2_800_000)

    @field_validator("cargo")
    @classmethod
    def valid_office(cls, value):
        office = normalize_office_name(value)
        if office is None:
            raise ValueError("Cargo desconhecido.")
        return office


class TelaoSave(StrictModel):
    versao: int = Field(ge=0)
    cards_por_pagina: int = Field(ge=1, le=12, strict=True)
    tempo_rotacao_segundos: int = Field(ge=5, le=300, strict=True)
    ativo: StrictBool = True
    candidatos: list[TelaoSelection] = Field(max_length=5000)

    @model_validator(mode="after")
    def unique_candidates(self):
        keys = [(c.cargo, candidate_key(c.numero)) for c in self.candidatos]
        if len(keys) != len(set(keys)):
            raise ValueError("O candidato já está selecionado para este cargo.")
        return self


class TelaoCandidate(StrictModel):
    id: UUID
    candidato_id: UUID | None
    cargo: str
    numero: str
    nome: str
    ordem: int
    ativo: bool
    foto_url: str | None


class TelaoConfigResponse(StrictModel):
    municipio: str
    municipio_codigo: str
    uf: str
    zona: str
    eleicao_data: date
    eleicao_turno: int
    cards_por_pagina: int
    tempo_rotacao_segundos: int
    ativo: bool
    versao: int
    updated_at: datetime | None
    cargos: list[str]
    candidatos: list[TelaoCandidate]


class DisplayCandidate(StrictModel):
    id: UUID
    ordem: int
    cargo: str
    numero: str
    nome: str
    votos: int
    foto_url: str | None


class AvailableCandidate(StrictModel):
    candidato_id: UUID
    cargo: str
    numero: str
    nome: str


class AvailableCandidates(StrictModel):
    candidatos: list[AvailableCandidate]
    tem_mais: bool


class DivulgacaoResponse(StrictModel):
    municipio: str
    uf: str
    zona: str
    eleicao_data: date
    eleicao_turno: int
    boletins_recebidos: int
    secoes_representadas: int
    total_secoes_esperadas: int | None
    urnas_apuradas: int
    total_urnas: int | None
    ultima_atualizacao: datetime
    ultima_importacao: datetime | None
    cards_por_pagina: int
    tempo_rotacao_segundos: int
    ativo: bool
    versao: int
    candidatos: list[DisplayCandidate]
