"""Add independent screen configuration, preserving the electoral import tables."""

from alembic import op
import sqlalchemy as sa

revision = "d13e840a6c27"
down_revision = "c92a617de408"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "telao_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("municipio_codigo", sa.String(20), nullable=False),
        sa.Column("municipio_nome", sa.String(200), nullable=False),
        sa.Column("uf", sa.String(2), nullable=False),
        sa.Column("zona", sa.String(20), nullable=False),
        sa.Column("eleicao_data", sa.Date(), nullable=False),
        sa.Column("eleicao_turno", sa.Integer(), nullable=False),
        sa.Column("cards_por_pagina", sa.Integer(), nullable=False),
        sa.Column("tempo_rotacao_segundos", sa.Integer(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("id = 1", name="ck_telao_singleton"),
        sa.CheckConstraint("cards_por_pagina BETWEEN 1 AND 12", name="ck_telao_cards"),
        sa.CheckConstraint("tempo_rotacao_segundos BETWEEN 5 AND 300", name="ck_telao_rotation"),
    )
    op.create_table(
        "telao_candidatos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "config_id",
            sa.Integer(),
            sa.ForeignKey("telao_config.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidato_id", sa.Uuid(), sa.ForeignKey("votos_candidatos.id", ondelete="SET NULL")
        ),
        sa.Column("cargo", sa.String(100), nullable=False),
        sa.Column("numero_candidato", sa.String(20), nullable=False),
        sa.Column("nome_candidato", sa.String(200), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("config_id", "cargo", "numero_candidato", name="uq_telao_candidate"),
        sa.UniqueConstraint(
            "config_id", "ordem", name="uq_telao_order", deferrable=True, initially="DEFERRED"
        ),
        sa.CheckConstraint("ordem > 0", name="ck_telao_order"),
    )
    op.create_index("ix_telao_candidatos_candidato_id", "telao_candidatos", ["candidato_id"])
    for table in ("telao_config", "telao_candidatos"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    # Never expose electoral rows through anonymous RLS policies. Only the server subscribes.
    op.execute("""DO $$ DECLARE t text; BEGIN
        IF current_schema() = 'public' AND EXISTS (
            SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime'
        ) THEN
            FOREACH t IN ARRAY ARRAY['boletins', 'secoes_esperadas', 'telao_config', 'telao_candidatos'] LOOP
                IF NOT EXISTS (SELECT 1 FROM pg_publication_tables
                    WHERE pubname = 'supabase_realtime' AND schemaname = 'public' AND tablename = t) THEN
                    EXECUTE format('ALTER PUBLICATION supabase_realtime ADD TABLE public.%I', t);
                END IF;
            END LOOP;
        END IF;
    END $$""")


def downgrade():
    op.drop_table("telao_candidatos")
    op.drop_table("telao_config")
