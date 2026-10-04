import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.candidato_voto import CandidatoVoto


class Resultado(Base):
    __tablename__ = "resultados"
    __table_args__ = (UniqueConstraint("boletim_id", "cargo", name="uq_resultado_cargo"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    boletim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("boletins.id", ondelete="CASCADE"), index=True
    )
    cargo: Mapped[str] = mapped_column(String(100))
    votos_nominais: Mapped[int | None]
    votos_legenda: Mapped[int | None] = mapped_column(default=0, server_default="0")
    brancos: Mapped[int | None]
    nulos: Mapped[int | None]
    total_apurado: Mapped[int | None]
    vagas: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default="[]")
    candidatos: Mapped[list["CandidatoVoto"]] = relationship(cascade="all, delete-orphan")
