from sqlalchemy.orm import Session
from database import SessionLocal
import models

def check_transactions():
    db = SessionLocal()
    try:
        txs = db.query(models.TransactionHistory).order_by(models.TransactionHistory.created_at.desc()).all()
        print(f"Total transactions found: {len(txs)}")
        for tx in txs:
            print(f"ID: {tx.id} | Ref: {tx.merchant_ref} | Plan: {tx.plan_sku} | Amount: {tx.amount} | Status: {tx.status} | Paid At: {tx.paid_at}")
    finally:
        db.close()

if __name__ == "__main__":
    check_transactions()
