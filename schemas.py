from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime

# Leads
class LeadBase(BaseModel):
    google_place_id: str
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    rating: Optional[float] = None
    category: Optional[str] = None
    is_saved: Optional[bool] = False

class LeadCreate(LeadBase):
    search_id: int

class LeadResponse(LeadBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class LeadSaveRequest(BaseModel):
    lead_id: int
    category: Optional[str] = "General"

class LeadSaveBatchRequest(BaseModel):
    lead_ids: List[int]
    category: Optional[str] = "General"

# Search
class SearchRequest(BaseModel):
    keyword: str
    location_name: str
    radius: float = 5.0 # km
    max_results: int = 20 # Default to 20

class SearchResponse(BaseModel):
    search_id: int
    keyword: str
    location_name: str
    total_results: int
    leads: List[LeadResponse]
    model_config = ConfigDict(from_attributes=True)

# Users
class UserBase(BaseModel):
    email: str

class UserCreate(UserBase):
    password: str
    name: Optional[str] = None

class UserResponse(UserBase):
    id: int
    name: Optional[str] = None
    plan_type: str
    credits: int
    fonnte_token: Optional[str] = None
    search_api_key: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    fonnte_token: Optional[str] = None
    search_api_key: Optional[str] = None

# Auth
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class GoogleLoginRequest(BaseModel):
    credential: str

# WhatsApp Broadcast
class MessageTemplateBase(BaseModel):
    name: str
    content: str

class MessageTemplateCreate(MessageTemplateBase):
    pass

class MessageTemplateResponse(MessageTemplateBase):
    id: int
    user_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class BroadcastRequest(BaseModel):
    lead_ids: List[int]
    device_id: Optional[int] = None
    template_id: Optional[int] = None
    custom_content: Optional[str] = None
    delay: Optional[int] = 3 # Default to 2 seconds for safety


# WhatsApp Device
class WhatsAppDeviceBase(BaseModel):
    name: str

class WhatsAppDeviceCreate(WhatsAppDeviceBase):
    device: str # Phone number for Fonnte creation

class WhatsAppDeviceUpdate(BaseModel):
    name: Optional[str] = None

class WhatsAppDeviceResponse(WhatsAppDeviceBase):
    id: int
    user_id: int
    device_number: Optional[str] = None
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# Message History
class MessageHistoryResponse(BaseModel):
    id: str
    user_id: int
    target: str
    message: str
    status: str
    state: Optional[str] = None
    stateid: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# Fonnte Webhook
class FonnteWebhookPayload(BaseModel):
    device: Optional[str] = None
    id: Optional[str] = None
    stateid: Optional[str] = None
    status: Optional[str] = None
    state: Optional[str] = None
    sender: Optional[str] = None
    message: Optional[str] = None
    member: Optional[str] = None
    name: Optional[str] = None
    pesan: Optional[str] = None  # incoming message text
    pengirim: Optional[str] = None  # sender number
    url: Optional[str] = None  # media url if any
    filename: Optional[str] = None
    extension: Optional[str] = None
    
    model_config = ConfigDict(extra='allow')  # Allow extra fields from Fonnte

# Fonnte Connection Webhook
class FonnteConnectPayload(BaseModel):
    device: Optional[str] = None
    status: Optional[str] = None  # "connect" or "disconnect"
    token: Optional[str] = None   # Device token from Fonnte
    
    model_config = ConfigDict(extra='allow')  # Allow extra fields from Fonnte

