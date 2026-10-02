"""Store independent screen candidate photos, without changing electoral results."""

from alembic import op
import sqlalchemy as sa

revision = "e52b7a91f603"
down_revision = "d13e840a6c27"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("telao_candidatos", sa.Column("foto_bucket", sa.String(100), nullable=True))
    op.add_column("telao_candidatos", sa.Column("foto_path", sa.String(500), nullable=True))


def downgrade():
    op.drop_column("telao_candidatos", "foto_path")
    op.drop_column("telao_candidatos", "foto_bucket")
