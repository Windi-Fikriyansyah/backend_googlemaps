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

class SavedLead(Base):
    __tablename__ = "user_saved_leads"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True)
    category = Column(String, default="General")
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    lead = relationship("Lead")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    name = Column(String, nullable=True)  # User's display name
    password_hash = Column(String)
    plan_type = Column(String, default="free")  # free/pro
    credits = Column(Integer, default=0)
    fonnte_token = Column(String, nullable=True)
    search_api_key = Column(String, nullable=True)

    searches = relationship("Search", back_populates="user")
    saved_leads_assoc = relationship("SavedLead", backref="user")
    saved_leads = relationship("Lead", secondary="user_saved_leads", back_populates="saved_by_users", overlaps="saved_leads_assoc,user")
    message_templates = relationship("MessageTemplate", back_populates="user")
    whatsapp_devices = relationship("WhatsAppDevice", back_populates="user")
    message_histories = relationship("MessageHistory", back_populates="user")
    transactions = relationship("TransactionHistory", back_populates="user")

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
    saved_by_users = relationship("User", secondary="user_saved_leads", back_populates="saved_leads", overlaps="saved_leads_assoc,user")


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
    credits_deducted = Column(Boolean, default=False)  # Track if credit for this message was deducted
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="message_histories")


class TransactionHistory(Base):
    __tablename__ = "transaction_histories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    merchant_ref = Column(String, unique=True, index=True)
    amount = Column(Integer)
    plan_sku = Column(String)
    status = Column(String, default="UNPAID") # UNPAID, PAID, EXPIRED, FAILED
    method = Column(String, nullable=True) # Payment method
    payment_url = Column(String, nullable=True)
    customer_name = Column(String, nullable=True)
    customer_email = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    paid_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="transactions")
