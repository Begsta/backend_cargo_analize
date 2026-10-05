"""Preserve fractional cargo mass and volume."""
from alembic import op
import sqlalchemy as sa

revision = "002_cargo_measurements"
down_revision = "001_lab2_schema"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("cargo_mass", "cargo_volume"):
        op.alter_column("cargos", name, existing_type=sa.Integer(), type_=sa.Float(), existing_nullable=False)


def downgrade():
    # Refuse a rollback that would silently lose fractional measurements.
    connection = op.get_bind()
    fractional = connection.execute(sa.text(
        "SELECT count(*) FROM cargos WHERE cargo_mass != trunc(cargo_mass) "
        "OR cargo_volume != trunc(cargo_volume)"
    )).scalar()
    if fractional:
        raise RuntimeError("Нельзя откатить миграцию: есть дробные масса или объём")
    for name in ("cargo_mass", "cargo_volume"):
        op.alter_column("cargos", name, existing_type=sa.Float(), type_=sa.Integer(),
                        postgresql_using=f"{name}::integer", existing_nullable=False)
