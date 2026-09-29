import uuid
from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BoletimSecao(Base):
    __tablename__ = "boletim_secoes"
    # Scope is repeated to enforce overlap prevention even for concurrent requests.
    __table_args__ = (
        UniqueConstraint(
            "eleicao_data",
            "eleicao_turno",
            "municipio_codigo",
            "zona",
            "secao_chave",
            name="uq_secao_representada",
        ),
        CheckConstraint("tipo IN ('PRINCIPAL', 'AGREGADA')", name="ck_secao_tipo"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    boletim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("boletins.id", ondelete="CASCADE"), index=True
    )
    numero_secao: Mapped[str] = mapped_column(String(20))
    secao_chave: Mapped[str] = mapped_column(String(20))
    tipo: Mapped[str] = mapped_column(String(10))
    eleicao_data: Mapped[date]
    eleicao_turno: Mapped[int]
    municipio_codigo: Mapped[str] = mapped_column(String(20))
    zona: Mapped[str] = mapped_column(String(20))
