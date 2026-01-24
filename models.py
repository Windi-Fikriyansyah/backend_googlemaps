from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

# Association table for Many-to-Many relationship
search_leads = Table(
    "search_leads",
    Base.metadata,
    Column("search_id", Integer, ForeignKey("searches.id", ondelete="CASCADE"), primary_key=True),
    Column("lead_id", Integer, ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True),
)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    plan_type = Column(String, default="free")  # free/pro

    searches = relationship("Search", back_populates="user")

class Search(Base):
    __tablename__ = "searches"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    keyword = Column(String, index=True)
    location_name = Column(String, index=True)
    radius = Column(Float)
    max_results = Column(Integer, default=20)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="searches")
    leads = relationship("Lead", secondary=search_leads, back_populates="searches")

class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    google_place_id = Column(String, unique=True, index=True) # Ensure uniqueness
    name = Column(String, index=True)
    address = Column(String)
    phone = Column(String, nullable=True)
    website = Column(String, nullable=True)
    rating = Column(Float, nullable=True)
    category = Column(String, nullable=True)

    searches = relationship("Search", secondary=search_leads, back_populates="leads")
