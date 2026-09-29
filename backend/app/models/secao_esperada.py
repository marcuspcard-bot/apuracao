import uuid
from datetime import date

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SecaoEsperada(Base):
    __tablename__ = "secoes_esperadas"
    __table_args__ = (
        UniqueConstraint(
            "eleicao_data", "eleicao_turno", "municipio_codigo", "zona_chave", "secao_chave",
            name="uq_secao_esperada",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    eleicao_data: Mapped[date]
    eleicao_turno: Mapped[int]
    municipio_codigo: Mapped[str] = mapped_column(String(20))
    zona: Mapped[str] = mapped_column(String(20))
    zona_chave: Mapped[str] = mapped_column(String(20))
    numero_secao: Mapped[str] = mapped_column(String(20))
    secao_chave: Mapped[str] = mapped_column(String(20))
    secao_principal: Mapped[str] = mapped_column(String(20))
    principal_chave: Mapped[str] = mapped_column(String(20))
