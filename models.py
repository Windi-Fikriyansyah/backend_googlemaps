from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

# Association table for Search - Lead relationship (History)
search_leads = Table(
    "search_leads",
    Base.metadata,
    Column("search_id", Integer, ForeignKey("searches.id", ondelete="CASCADE"), primary_key=True),
    Column("lead_id", Integer, ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True),
)

# Association table for User - Lead relationship (Saved Leads)
user_saved_leads = Table(
    "user_saved_leads",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("lead_id", Integer, ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True),
    Column("timestamp", DateTime(timezone=True), server_default=func.now()),
)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    name = Column(String, nullable=True)  # User's display name
    password_hash = Column(String)
    plan_type = Column(String, default="free")  # free/pro

    searches = relationship("Search", back_populates="user")
    saved_leads = relationship("Lead", secondary=user_saved_leads, back_populates="saved_by_users")
    message_templates = relationship("MessageTemplate", back_populates="user")
    whatsapp_devices = relationship("WhatsAppDevice", back_populates="user")
    message_histories = relationship("MessageHistory", back_populates="user")

class MessageTemplate(Base):
    __tablename__ = "message_templates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String)
    content = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="message_templates")


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
    saved_by_users = relationship("User", secondary=user_saved_leads, back_populates="saved_leads")


class WhatsAppDevice(Base):
    __tablename__ = "whatsapp_devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String)
    device_number = Column(String) # Phone number / device identifier
    token = Column(String)  # Fonnte Device Token
    status = Column(String, default="disconnected")  # disconnected, connected, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="whatsapp_devices")


class MessageHistory(Base):
    __tablename__ = "message_histories"

    id = Column(String, primary_key=True, index=True) # Fonnte Message ID
    user_id = Column(Integer, ForeignKey("users.id"))
    target = Column(String, index=True)
    message = Column(String)
    status = Column(String) # sent, pending, etc.
    state = Column(String, nullable=True) # from webhook
    stateid = Column(String, nullable=True) # from webhook
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="message_histories")
