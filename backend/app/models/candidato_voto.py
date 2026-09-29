import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CandidatoVoto(Base):
    __tablename__ = "votos_candidatos"
    __table_args__ = (
        UniqueConstraint(
            "resultado_id", "numero_candidato", "vaga", name="uq_candidato_resultado_vaga"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    resultado_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resultados.id", ondelete="CASCADE"), index=True
    )
    numero_candidato: Mapped[str] = mapped_column(String(20))
    nome_candidato: Mapped[str] = mapped_column(String(200))
    votos: Mapped[int]
    vaga: Mapped[str] = mapped_column(String(100), default="", server_default="")
