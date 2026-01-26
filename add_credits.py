import sys
from sqlalchemy.orm import Session
from database import SessionLocal
import models

def add_credits(user_id: int, amount: int):
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if user:
            old_credits = user.credits or 0
            user.credits = old_credits + amount
            db.commit()
            print(f"SUCCESS: Added {amount} credits to User {user_id} ({user.email}).")
            print(f"New balance: {user.credits}")
        else:
            print(f"ERROR: User {user_id} not found.")
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python add_credits.py <user_id> <amount>")
        print("Example: python add_credits.py 1 1000")
        # Default for convenience if run without args
        add_credits(1, 1000)
    else:
        add_credits(int(sys.argv[1]), int(sys.argv[2]))
