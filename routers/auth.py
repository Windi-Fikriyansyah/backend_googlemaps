from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from google.oauth2 import id_token
from google.auth.transport import requests

import os
from dotenv import load_dotenv
import models, schemas, database

load_dotenv()

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key-for-dev-only") 
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 24 hours
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

router = APIRouter(prefix="/auth", tags=["auth"])

def get_current_user(request: Request, db: Session = Depends(database.get_db)):
    # Prioritize Authorization header for modern frontend apps
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        
    if not token:
        # Fallback to cookie
        token = request.cookies.get("access_token")
    
    if not token:
        return None

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
    except JWTError:
        return None
        
    user = db.query(models.User).filter(models.User.email == email).first()
    return user

def get_current_user_strict(user: models.User = Depends(get_current_user)):
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

# Helpers
# Bcrypt has a maximum password length of 72 bytes
def verify_password(plain_password, hashed_password):
    # Truncate password to 72 bytes to prevent bcrypt error in production
    truncated_password = plain_password[:72] if plain_password else plain_password
    return pwd_context.verify(truncated_password, hashed_password)

def get_password_hash(password):
    # Truncate password to 72 bytes to prevent bcrypt error in production
    truncated_password = password[:72] if password else password
    return pwd_context.hash(truncated_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@router.post("/register", response_model=schemas.UserResponse)
def register(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    new_user = models.User(email=user.email, name=user.name, password_hash=hashed_password, credits=50)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/login")
def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="email dan password salah",
        )
    
    access_token = create_access_token(data={"sub": user.email})
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=False, # Set to True in production with HTTPS
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "message": "Logged in successfully",
        "user": {"email": user.email}
    }

@router.post("/google")
def google_login(response: Response, request: schemas.GoogleLoginRequest, db: Session = Depends(database.get_db)):
    try:
        if not GOOGLE_CLIENT_ID:
            raise HTTPException(status_code=500, detail="Google Client ID not configured on server")
            
        idinfo = id_token.verify_oauth2_token(request.credential, requests.Request(), GOOGLE_CLIENT_ID)
        email = idinfo['email']
        name = idinfo.get('name', None)  # Get name from Google profile
        
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            user = models.User(email=email, name=name, password_hash="google-auth-no-password", plan_type="free", credits=50)
            db.add(user)
            db.commit()
            db.refresh(user)
        elif not user.name and name:
            # Update name if user exists but has no name
            user.name = name
            db.commit()
            
        access_token = create_access_token(data={"sub": user.email})
        
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            samesite="lax",
            secure=False,
        )
        return {
            "access_token": access_token, 
            "token_type": "bearer",
            "message": "Logged in successfully", 
            "user": {"email": user.email}
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Google token: {str(e)}")

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="access_token")
    return {"message": "Logged out successfully"}

@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(get_current_user_strict)):
    return current_user

@router.put("/me", response_model=schemas.UserResponse)
def update_me(
    user_data: schemas.UserUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    if user_data.name is not None:
        current_user.name = user_data.name
    if user_data.email is not None:
        # Check if email is already taken
        if user_data.email != current_user.email:
            existing_user = db.query(models.User).filter(models.User.email == user_data.email).first()
            if existing_user:
                raise HTTPException(status_code=400, detail="Email already registered")
            current_user.email = user_data.email
    if user_data.password is not None:
        current_user.password_hash = get_password_hash(user_data.password)
    if user_data.fonnte_token is not None:
        current_user.fonnte_token = user_data.fonnte_token
    if user_data.search_api_key is not None:
        current_user.search_api_key = user_data.search_api_key
        
    db.commit()
    db.refresh(current_user)
    return current_user
