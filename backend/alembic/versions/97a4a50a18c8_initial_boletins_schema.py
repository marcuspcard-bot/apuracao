"""initial boletins schema"""

from alembic import op
import sqlalchemy as sa

revision = "97a4a50a18c8"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "boletins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("eleicao_descricao", sa.String(length=200), nullable=False),
        sa.Column("eleicao_turno", sa.Integer(), nullable=False),
        sa.Column("eleicao_data", sa.Date(), nullable=False),
        sa.Column("municipio_codigo", sa.String(length=20), nullable=False),
        sa.Column("municipio_nome", sa.String(length=200), nullable=False),
        sa.Column("zona", sa.String(length=20), nullable=False),
        sa.Column("local_votacao", sa.String(length=20), nullable=False),
        sa.Column("secao", sa.String(length=20), nullable=False),
        sa.Column("quantidade_secoes_agregadas", sa.Integer(), nullable=False),
        sa.Column("eleitores_aptos", sa.Integer(), nullable=False),
        sa.Column("comparecimento", sa.Integer(), nullable=False),
        sa.Column("faltosos", sa.Integer(), nullable=False),
        sa.Column("codigo_urna", sa.String(length=20), nullable=False),
        sa.Column("data_abertura", sa.Date(), nullable=False),
        sa.Column("hora_abertura", sa.Time(), nullable=False),
        sa.Column("data_fechamento", sa.Date(), nullable=False),
        sa.Column("hora_fechamento", sa.Time(), nullable=False),
        sa.Column("assinatura_qrcode", sa.String(), nullable=False),
        sa.Column("codigo_carga", sa.String(length=100), nullable=False),
        sa.Column("arquivo_nome_original", sa.String(length=255), nullable=False),
        sa.Column("arquivo_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_bucket", sa.String(length=100), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("arquivo_hash"),
        sa.UniqueConstraint(
            "eleicao_data",
            "eleicao_turno",
            "municipio_codigo",
            "zona",
            "secao",
            name="uq_boletim_secao",
        ),
    )
    op.create_index(op.f("ix_boletins_created_at"), "boletins", ["created_at"], unique=False)
    op.create_table(
        "boletim_secoes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("boletim_id", sa.Uuid(), nullable=False),
        sa.Column("numero_secao", sa.String(length=20), nullable=False),
        sa.Column("secao_chave", sa.String(length=20), nullable=False),
        sa.Column("tipo", sa.String(length=10), nullable=False),
        sa.Column("eleicao_data", sa.Date(), nullable=False),
        sa.Column("eleicao_turno", sa.Integer(), nullable=False),
        sa.Column("municipio_codigo", sa.String(length=20), nullable=False),
        sa.Column("zona", sa.String(length=20), nullable=False),
        sa.CheckConstraint("tipo IN ('PRINCIPAL', 'AGREGADA')", name="ck_secao_tipo"),
        sa.ForeignKeyConstraint(["boletim_id"], ["boletins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "eleicao_data",
            "eleicao_turno",
            "municipio_codigo",
            "zona",
            "secao_chave",
            name="uq_secao_representada",
        ),
    )
    op.create_index(
        op.f("ix_boletim_secoes_boletim_id"), "boletim_secoes", ["boletim_id"], unique=False
    )
    op.create_table(
        "resultados",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("boletim_id", sa.Uuid(), nullable=False),
        sa.Column("cargo", sa.String(length=100), nullable=False),
        sa.Column("votos_nominais", sa.Integer(), nullable=False),
        sa.Column("brancos", sa.Integer(), nullable=False),
        sa.Column("nulos", sa.Integer(), nullable=False),
        sa.Column("total_apurado", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["boletim_id"], ["boletins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("boletim_id", "cargo", name="uq_resultado_cargo"),
    )
    op.create_index(op.f("ix_resultados_boletim_id"), "resultados", ["boletim_id"], unique=False)
    op.create_table(
        "votos_candidatos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("resultado_id", sa.Uuid(), nullable=False),
        sa.Column("numero_candidato", sa.String(length=20), nullable=False),
        sa.Column("nome_candidato", sa.String(length=200), nullable=False),
        sa.Column("votos", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["resultado_id"], ["resultados.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resultado_id", "numero_candidato", name="uq_candidato_resultado"),
    )
    op.create_index(
        op.f("ix_votos_candidatos_resultado_id"), "votos_candidatos", ["resultado_id"], unique=False
    )
    for table in ("boletins", "boletim_secoes", "resultados", "votos_candidatos"):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))


def downgrade():
    op.drop_index(op.f("ix_votos_candidatos_resultado_id"), table_name="votos_candidatos")
    op.drop_table("votos_candidatos")
    op.drop_index(op.f("ix_resultados_boletim_id"), table_name="resultados")
    op.drop_table("resultados")
    op.drop_index(op.f("ix_boletim_secoes_boletim_id"), table_name="boletim_secoes")
    op.drop_table("boletim_secoes")
    op.drop_index(op.f("ix_boletins_created_at"), table_name="boletins")
    op.drop_table("boletins")
