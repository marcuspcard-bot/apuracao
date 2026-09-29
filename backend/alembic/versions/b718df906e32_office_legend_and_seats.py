"""Preserve legend votes and explicit Senate seats without deriving missing totals."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b718df906e32"
down_revision = "97a4a50a18c8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "resultados", sa.Column("votos_legenda", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "resultados",
        sa.Column(
            "vagas", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )
    for column in ("votos_nominais", "brancos", "nulos", "total_apurado"):
        op.alter_column("resultados", column, existing_type=sa.Integer(), nullable=True)
    op.add_column(
        "votos_candidatos", sa.Column("vaga", sa.String(100), nullable=False, server_default="")
    )
    op.drop_constraint("uq_candidato_resultado", "votos_candidatos", type_="unique")
    op.create_unique_constraint(
        "uq_candidato_resultado_vaga",
        "votos_candidatos",
        ["resultado_id", "numero_candidato", "vaga"],
    )


def downgrade():
    # Prevent silent loss of seat/legend information when returning to the old schema.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM resultados WHERE votos_legenda <> 0 OR vagas <> '[]'::jsonb
                   OR votos_nominais IS NULL OR brancos IS NULL OR nulos IS NULL OR total_apurado IS NULL)
           OR EXISTS (SELECT 1 FROM votos_candidatos WHERE vaga <> '') THEN
            RAISE EXCEPTION 'Downgrade bloqueado: existem votos de legenda ou vagas estruturadas.';
        END IF;
    END $$""")
    op.drop_constraint("uq_candidato_resultado_vaga", "votos_candidatos", type_="unique")
    op.create_unique_constraint(
        "uq_candidato_resultado", "votos_candidatos", ["resultado_id", "numero_candidato"]
    )
    op.drop_column("votos_candidatos", "vaga")
    for column in ("votos_nominais", "brancos", "nulos", "total_apurado"):
        op.alter_column("resultados", column, existing_type=sa.Integer(), nullable=False)
    op.drop_column("resultados", "vagas")
    op.drop_column("resultados", "votos_legenda")
