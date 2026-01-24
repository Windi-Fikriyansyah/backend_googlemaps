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
        
        # Create Many-to-Many association table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS search_leads (
                search_id INTEGER REFERENCES searches(id) ON DELETE CASCADE,
                lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
                PRIMARY KEY (search_id, lead_id)
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
    allow_origins=["*"], # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(leads.router)
app.include_router(auth.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to Lead Gen API"}

# For running with python main.py locally if desired
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
