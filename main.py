from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from database import engine, Base, SessionLocal
from routers import leads, auth
import models
import uvicorn

# Create tables
Base.metadata.create_all(bind=engine)

# Automatic Migration for newly added columns and tables
with engine.connect() as conn:
    try:
        print("Running automatic database migrations...")
        conn.execute(text("ALTER TABLE searches ADD COLUMN IF NOT EXISTS keyword VARCHAR"))
        conn.execute(text("ALTER TABLE searches ADD COLUMN IF NOT EXISTS location_name VARCHAR"))
        conn.execute(text("ALTER TABLE searches ADD COLUMN IF NOT EXISTS radius FLOAT"))
        conn.execute(text("ALTER TABLE searches ADD COLUMN IF NOT EXISTS max_results INTEGER DEFAULT 20"))
        
        # Create Many-to-Many association table for search results
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS search_leads (
                search_id INTEGER REFERENCES searches(id) ON DELETE CASCADE,
                lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
                PRIMARY KEY (search_id, lead_id)
            )
        """))
        
        # Create Many-to-Many association table for Saved Leads
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_saved_leads (
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, lead_id)
            )
        """))
        
        # Create message_templates table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS message_templates (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                name VARCHAR,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # Create whatsapp_devices table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS whatsapp_devices (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                name VARCHAR,
                device_number VARCHAR,
                token VARCHAR,
                status VARCHAR DEFAULT 'disconnected',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # Ensure device_number column exists for existing tables
        conn.execute(text("ALTER TABLE whatsapp_devices ADD COLUMN IF NOT EXISTS device_number VARCHAR"))
        # Add name column to users table
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR"))
        # Add credits column to users table
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS credits INTEGER DEFAULT 0"))
        # Add credits_deducted column to message_histories table
        conn.execute(text("ALTER TABLE message_histories ADD COLUMN IF NOT EXISTS credits_deducted BOOLEAN DEFAULT FALSE"))
        # Create transaction_histories table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS transaction_histories (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                merchant_ref VARCHAR UNIQUE,
                amount INTEGER,
                plan_sku VARCHAR,
                status VARCHAR DEFAULT 'UNPAID',
                method VARCHAR,
                payment_url VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP
            )
        """))
        conn.commit()
    except Exception as e:
        print(f"Auto-migration info (this might be normal): {e}")

# Seed default user if not exists
db = SessionLocal()
try:
    if not db.query(models.User).filter(models.User.id == 1).first():
        default_user = models.User(
            id=1,
            email="admin@example.com",
            password_hash="hashed_password", # Placeholder
            plan_type="pro"
        )
        db.add(default_user)
        db.commit()
finally:
    db.close()

app = FastAPI(title="Lead Generation API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://wamaps.myxyzz.online", "http://localhost:3000"], # Updated for current dev port
    allow_credentials=True,

    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(leads.router)
app.include_router(auth.router)
from routers import whatsapp, payment
app.include_router(whatsapp.router)
app.include_router(payment.router)


@app.get("/")
def read_root():
    return {"message": "Welcome to Lead Gen API"}

# For running with python main.py locally if desired
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
