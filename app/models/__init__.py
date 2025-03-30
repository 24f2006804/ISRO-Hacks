from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Item(Base):
    __tablename__ = "items"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    width = Column(Float, nullable=False)
    depth = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    mass = Column(Float, nullable=False)
    priority = Column(Integer, nullable=False)
    expiry_date = Column(DateTime, nullable=True)
    usage_limit = Column(Integer, nullable=True)
    uses_remaining = Column(Integer, nullable=True)
    preferred_zone = Column(String, nullable=False)
    container_id = Column(String, ForeignKey("containers.id"), nullable=True)
    position = Column(JSON, nullable=True)  # Stores position data as JSON
    is_waste = Column(Boolean, default=False)

    container = relationship("Container", back_populates="items")

class Container(Base):
    __tablename__ = "containers"

    id = Column(String, primary_key=True)
    zone = Column(String, nullable=False)
    width = Column(Float, nullable=False)
    depth = Column(Float, nullable=False)
    height = Column(Float, nullable=False)

    items = relationship("Item", back_populates="container")

class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False)
    user_id = Column(String, nullable=False)
    action_type = Column(String, nullable=False)
    item_id = Column(String, ForeignKey("items.id"), nullable=False)
    details = Column(JSON, nullable=True)  # Additional action details as JSON

    item = relationship("Item")