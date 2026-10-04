"""Partial manual bulletins and replacement audit trail."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f64c820ab931"
down_revision = "e52b7a91f603"
branch_labels = None
depends_on = None

FIELDS = (
    "local_votacao",
    "eleitores_aptos",
    "comparecimento",
    "faltosos",
    "codigo_urna",
    "data_abertura",
    "hora_abertura",
    "data_fechamento",
    "hora_fechamento",
    "assinatura_qrcode",
    "codigo_carga",
)


def upgrade():
    op.alter_column("resultados", "votos_legenda", nullable=True)
    op.add_column(
        "boletins", sa.Column("origem", sa.String(10), nullable=False, server_default="PDF")
    )
    op.add_column(
        "boletins",
        sa.Column("historico_manual", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column("boletins", sa.Column("evidencia_bucket", sa.String(100)))
    op.add_column("boletins", sa.Column("evidencia_path", sa.String(500)))
    for field in FIELDS:
        op.alter_column("boletins", field, nullable=True)


def downgrade():
    op.alter_column("resultados", "votos_legenda", nullable=False)
    # Refuse downgrade while partial records still exist; never invent missing data.
    for field in FIELDS:
        op.alter_column("boletins", field, nullable=False)
    for field in ("evidencia_path", "evidencia_bucket", "historico_manual", "origem"):
        op.drop_column("boletins", field)
