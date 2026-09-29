import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TelaoConfig(Base):
    __tablename__ = "telao_config"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_telao_singleton"),
        CheckConstraint("cards_por_pagina BETWEEN 1 AND 12", name="ck_telao_cards"),
        CheckConstraint("tempo_rotacao_segundos BETWEEN 5 AND 300", name="ck_telao_rotation"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    municipio_codigo: Mapped[str] = mapped_column(String(20))
    municipio_nome: Mapped[str] = mapped_column(String(200))
    uf: Mapped[str] = mapped_column(String(2))
    zona: Mapped[str] = mapped_column(String(20))
    eleicao_data: Mapped[date]
    eleicao_turno: Mapped[int]
    cards_por_pagina: Mapped[int]
    tempo_rotacao_segundos: Mapped[int]
    ativo: Mapped[bool]
    versao: Mapped[int]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    candidatos: Mapped[list["TelaoCandidato"]] = relationship(
        cascade="all, delete-orphan", order_by="TelaoCandidato.ordem"
    )


class TelaoCandidato(Base):
    __tablename__ = "telao_candidatos"
    __table_args__ = (
        UniqueConstraint("config_id", "cargo", "numero_candidato", name="uq_telao_candidate"),
        UniqueConstraint(
            "config_id", "ordem", name="uq_telao_order", deferrable=True, initially="DEFERRED"
        ),
        CheckConstraint("ordem > 0", name="ck_telao_order"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    config_id: Mapped[int] = mapped_column(ForeignKey("telao_config.id", ondelete="CASCADE"))
    # Existing candidate rows belong to individual BUs, not a global candidate catalog.
    candidato_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("votos_candidatos.id", ondelete="SET NULL"), index=True
    )
    cargo: Mapped[str] = mapped_column(String(100))
    numero_candidato: Mapped[str] = mapped_column(String(20))
    nome_candidato: Mapped[str] = mapped_column(String(200))
    ordem: Mapped[int]
    ativo: Mapped[bool]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
