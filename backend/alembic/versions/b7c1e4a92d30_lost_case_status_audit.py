"""Record who changed a lost-person case status and when."""
from alembic import op
import sqlalchemy as sa

revision = "b7c1e4a92d30"
down_revision = "a91c7d2e6f40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lost_person_cases", sa.Column("status_changed_by", sa.String(length=36), nullable=True))
    op.add_column("lost_person_cases", sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("lost_person_cases", "status_changed_at")
    op.drop_column("lost_person_cases", "status_changed_by")
