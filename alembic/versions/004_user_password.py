"""Add password hashes; existing lab 3 users remain without login access."""

import sqlalchemy as sa

from alembic import op

revision = "004_user_password"
down_revision = "003_optional_cargo_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_hash")
