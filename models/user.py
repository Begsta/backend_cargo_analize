from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from db.base import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    user_login = Column(String(64), nullable=False, unique=True)
    user_name = Column(String(128), nullable=False)
    password_hash = Column(String(512), nullable=True)

    cargos = relationship("Cargo", back_populates="creator")
    likes = relationship("Like", back_populates="user")
