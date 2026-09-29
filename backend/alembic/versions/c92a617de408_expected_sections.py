"""Add the expected section registry without modifying imported bulletins."""

from alembic import op
import sqlalchemy as sa

revision = "c92a617de408"
down_revision = "b718df906e32"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "secoes_esperadas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("eleicao_data", sa.Date(), nullable=False),
        sa.Column("eleicao_turno", sa.Integer(), nullable=False),
        sa.Column("municipio_codigo", sa.String(20), nullable=False),
        sa.Column("zona", sa.String(20), nullable=False),
        sa.Column("zona_chave", sa.String(20), nullable=False),
        sa.Column("numero_secao", sa.String(20), nullable=False),
        sa.Column("secao_chave", sa.String(20), nullable=False),
        sa.Column("secao_principal", sa.String(20), nullable=False),
        sa.Column("principal_chave", sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "eleicao_data", "eleicao_turno", "municipio_codigo", "zona_chave", "secao_chave",
            name="uq_secao_esperada",
        ),
    )
    op.execute("ALTER TABLE secoes_esperadas ENABLE ROW LEVEL SECURITY")


def downgrade():
    op.drop_table("secoes_esperadas")
