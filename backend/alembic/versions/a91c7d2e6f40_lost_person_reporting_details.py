"""Store public lost-person report and contact details."""
from alembic import op
import sqlalchemy as sa

revision = "a91c7d2e6f40"
down_revision = "550fab2a684c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("lost_person_cases") as batch:
        batch.alter_column("photo_ref", type_=sa.Text(), existing_type=sa.String(length=240), existing_nullable=True)
    op.add_column("lost_person_cases", sa.Column("languages_spoken", sa.String(length=240), nullable=True))
    op.add_column("lost_person_cases", sa.Column("medical_needs", sa.String(length=500), nullable=True))
    op.add_column("lost_person_cases", sa.Column("reporter_name", sa.String(length=120), nullable=True))
    op.add_column("lost_person_cases", sa.Column("reporter_phone", sa.String(length=10), nullable=True))
    op.add_column("lost_person_cases", sa.Column("reporter_relation", sa.String(length=40), nullable=True))
    op.add_column("lost_person_cases", sa.Column("alternate_phone", sa.String(length=10), nullable=True))
    op.add_column("lost_person_cases", sa.Column("reporter_location", sa.String(length=160), nullable=True))
    op.create_index(op.f("ix_lost_person_cases_reporter_phone"), "lost_person_cases", ["reporter_phone"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_lost_person_cases_reporter_phone"), table_name="lost_person_cases")
    op.drop_column("lost_person_cases", "reporter_location")
    op.drop_column("lost_person_cases", "alternate_phone")
    op.drop_column("lost_person_cases", "reporter_relation")
    op.drop_column("lost_person_cases", "reporter_phone")
    op.drop_column("lost_person_cases", "reporter_name")
    op.drop_column("lost_person_cases", "medical_needs")
    op.drop_column("lost_person_cases", "languages_spoken")
    with op.batch_alter_table("lost_person_cases") as batch:
        batch.alter_column("photo_ref", type_=sa.String(length=240), existing_type=sa.Text(), existing_nullable=True)
