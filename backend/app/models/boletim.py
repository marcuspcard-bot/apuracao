import uuid
from datetime import date, datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.secao import BoletimSecao
    from app.models.resultado import Resultado


class Boletim(Base):
    __tablename__ = "boletins"
    __table_args__ = (
        UniqueConstraint(
            "eleicao_data",
            "eleicao_turno",
            "municipio_codigo",
            "zona",
            "secao",
            name="uq_boletim_secao",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    eleicao_descricao: Mapped[str] = mapped_column(String(200))
    eleicao_turno: Mapped[int]
    eleicao_data: Mapped[date]
    municipio_codigo: Mapped[str] = mapped_column(String(20))
    municipio_nome: Mapped[str] = mapped_column(String(200))
    zona: Mapped[str] = mapped_column(String(20))
    local_votacao: Mapped[str] = mapped_column(String(20))
    secao: Mapped[str] = mapped_column(String(20))
    quantidade_secoes_agregadas: Mapped[int]
    eleitores_aptos: Mapped[int]
    comparecimento: Mapped[int]
    faltosos: Mapped[int]
    codigo_urna: Mapped[str] = mapped_column(String(20))
    data_abertura: Mapped[date]
    hora_abertura: Mapped[time]
    data_fechamento: Mapped[date]
    hora_fechamento: Mapped[time]
    assinatura_qrcode: Mapped[str]
    codigo_carga: Mapped[str] = mapped_column(String(100))
    arquivo_nome_original: Mapped[str] = mapped_column(String(255))
    arquivo_hash: Mapped[str] = mapped_column(String(64), unique=True)
    storage_bucket: Mapped[str] = mapped_column(String(100))
    storage_path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    secoes: Mapped[list["BoletimSecao"]] = relationship(cascade="all, delete-orphan")
    resultados: Mapped[list["Resultado"]] = relationship(cascade="all, delete-orphan")

    @property
    def total_secoes_representadas(self) -> int:
        return 1 + self.quantidade_secoes_agregadas
