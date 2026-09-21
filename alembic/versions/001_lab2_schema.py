"""create users cargos interest_marks

Revision ID: 001_lab2_schema
Revises:
Create Date: 2026-09-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_lab2_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_login", sa.String(length=64), nullable=False),
        sa.Column("user_name", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("user_login"),
    )

    op.create_table(
        "cargos",
        sa.Column("cargo_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cargo_name", sa.String(length=256), nullable=False),
        sa.Column("cargo_description", sa.Text(), nullable=False),
        sa.Column("publication_status", sa.String(length=32), nullable=False),
        sa.Column("image_url", sa.String(length=512), nullable=False),
        sa.Column("video_url", sa.String(length=512), nullable=False),
        sa.Column("cargo_mass", sa.Integer(), nullable=False),
        sa.Column("cargo_volume", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("formed_at", sa.DateTime(), nullable=False),
        sa.Column("creator_user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["creator_user_id"],
            ["users.user_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("cargo_id"),
    )

    op.create_index(
        "uq_cargos_one_draft_per_creator",
        "cargos",
        ["creator_user_id"],
        unique=True,
        postgresql_where=sa.text("publication_status = 'draft'"),
    )

    op.create_table(
        "cargo_interest_marks",
        sa.Column("mark_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("cargo_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cargo_id"],
            ["cargos.cargo_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("mark_id"),
        sa.UniqueConstraint("user_id", "cargo_id", name="uq_interest_user_cargo"),
    )


def downgrade() -> None:
    op.drop_table("cargo_interest_marks")
    op.drop_index(
        "uq_cargos_one_draft_per_creator",
        table_name="cargos",
        postgresql_where=sa.text("publication_status = 'draft'"),
    )
    op.drop_table("cargos")
    op.drop_table("users")
