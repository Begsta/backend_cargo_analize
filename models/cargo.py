from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Float, Integer, String, Text
from sqlalchemy.orm import relationship

from db.base import Base

STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"
STATUS_DELETED = "deleted"


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Cargo(Base):
    __tablename__ = "cargos"

    cargo_id = Column(Integer, primary_key=True, index=True)
    cargo_name = Column(String(256), nullable=False)
    cargo_description = Column(Text, nullable=False, default="")
    publication_status = Column(String(32), nullable=False)
    image_url = Column(String(512), nullable=False, default="")
    video_url = Column(String(512), nullable=False, default="")
    cargo_mass = Column(Float, nullable=False, default=0)
    cargo_volume = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    formed_at = Column(DateTime, nullable=False, default=utc_now)
    creator_user_id = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )

    creator = relationship("User", back_populates="cargos")
    likes = relationship("Like", back_populates="cargo")
