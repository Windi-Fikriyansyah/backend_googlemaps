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

class LeadCreate(LeadBase):
    search_id: int

class LeadResponse(LeadBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

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

class UserResponse(UserBase):
    id: int
    plan_type: str
    model_config = ConfigDict(from_attributes=True)

# Auth
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class GoogleLoginRequest(BaseModel):
    credential: str
