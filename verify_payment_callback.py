import hmac
import hashlib
import json
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path="d:/maps/backend/.env")

from database import SessionLocal
import models

PRIVATE_KEY = os.getenv("TRIPAY_PRIVATE_KEY")
BACKEND_URL = "http://localhost:8000"

def test_tripay_callback(status="PAID"):
    print(f"\n--- Starting Tripay Callback Verification for status: {status} ---")
    
    merchant_ref = f"INV-micro-123456789-{status}"
    
    # Pre-create transaction record
    db = SessionLocal()
    try:
        # Delete if exists
        db.query(models.TransactionHistory).filter(models.TransactionHistory.merchant_ref == merchant_ref).delete()
        
        new_tx = models.TransactionHistory(
            user_id=1,
            merchant_ref=merchant_ref,
            amount=50000,
            plan_sku="micro",
            status="UNPAID"
        )
        db.add(new_tx)
        db.commit()
        print(f"Created initial UNPAID transaction: {merchant_ref}")
    finally:
        db.close()

    # Mock payload with NEW format (INV-SKU-TIMESTAMP-USERID)
    payload = {
        "status": status,
        "merchant_ref": merchant_ref,
        "payment_method": "BRIVA"
    }
    
    body = json.dumps(payload).encode()
    
    # Create signature
    signature = hmac.new(
        PRIVATE_KEY.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        "X-Callback-Signature": signature,
        "Content-Type": "application/json"
    }
    
    print(f"Sending mock callback to {BACKEND_URL}/payments/callback...")
    try:
        response = requests.post(f"{BACKEND_URL}/payments/callback", data=body, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200 and response.json().get("success"):
            print(f"Server Response SUCCESS for {status}")
            # Check DB
            db = SessionLocal()
            try:
                tx = db.query(models.TransactionHistory).filter(models.TransactionHistory.merchant_ref == merchant_ref).first()
                if tx and tx.status == status:
                    print(f"DB VERIFIED: Transaction {merchant_ref} status is now {tx.status}")
                else:
                    print(f"DB FAILED: Transaction {merchant_ref} not updated correctly in DB. Final status: {tx.status if tx else 'None'}")
            finally:
                db.close()
        else:
            print("Verification FAILED: Callback returned error.")
            
    except Exception as e:
        print(f"Connection failed: {e}")
        print("Make sure the backend server is running on port 8000.")

if __name__ == "__main__":
    if not PRIVATE_KEY:
        print("ERROR: TRIPAY_PRIVATE_KEY not found in .env")
    else:
        test_tripay_callback("PAID")
        test_tripay_callback("EXPIRED")
        test_tripay_callback("FAILED")
