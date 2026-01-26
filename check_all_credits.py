from sqlalchemy.orm import Session
from database import SessionLocal
import models

def check_all_credits():
    db = SessionLocal()
    try:
        users = db.query(models.User).all()
        print(f"Total users found: {len(users)}")
        for user in users:
            print(f"ID: {user.id} | Email: {user.email} | Credits: {user.credits}")
    finally:
        db.close()

if __name__ == "__main__":
    check_all_credits()
