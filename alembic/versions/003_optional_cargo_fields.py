"""Allow omitted description, mass and volume to be stored as SQL NULL."""
from alembic import op
import sqlalchemy as sa

revision = "003_optional_cargo_fields"
down_revision = "002_cargo_measurements"
branch_labels = None
depends_on = None

FIELDS = {"cargo_description": sa.Text(), "cargo_mass": sa.Float(), "cargo_volume": sa.Float()}


def upgrade():
    for name, column_type in FIELDS.items():
        op.alter_column("cargos", name, existing_type=column_type, nullable=True, server_default=None)


def downgrade():
    connection = op.get_bind()
    missing = connection.execute(sa.text(
        "SELECT count(*) FROM cargos WHERE cargo_description IS NULL "
        "OR cargo_mass IS NULL OR cargo_volume IS NULL"
    )).scalar()
    if missing:
        raise RuntimeError("Нельзя откатить миграцию: есть незаполненные необязательные поля")
    for name, column_type in FIELDS.items():
        op.alter_column("cargos", name, existing_type=column_type, nullable=False)
