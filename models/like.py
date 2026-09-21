from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from db.base import Base


class Like(Base):
    __tablename__ = "cargo_interest_marks"
    __table_args__ = (
        UniqueConstraint("user_id", "cargo_id", name="uq_interest_user_cargo"),
    )

    mark_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    cargo_id = Column(
        Integer,
        ForeignKey("cargos.cargo_id", ondelete="RESTRICT"),
        nullable=False,
    )

    user = relationship("User", back_populates="likes")
    cargo = relationship("Cargo", back_populates="likes")
