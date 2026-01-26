from sqlalchemy.orm import Session
from database import SessionLocal
import models

def check_user_credits(user_id: int):
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if user:
            print(f"User {user_id} ({user.email}) credits: {user.credits}")
        else:
            print(f"User {user_id} not found.")
    finally:
        db.close()

if __name__ == "__main__":
    check_user_credits(1)
