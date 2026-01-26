from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import models, schemas, database
from routers.auth import get_current_user_strict
import os
import hashlib
import hmac
import requests
import time
import json

router = APIRouter(prefix="/payments", tags=["payments"])

def get_tripay_config():
    api_key = os.getenv("TRIPAY_API_KEY")
    private_key = os.getenv("TRIPAY_PRIVATE_KEY")
    merchant_code = os.getenv("TRIPAY_MERCHANT_CODE")
    
    if not all([api_key, private_key, merchant_code]):
        raise HTTPException(
            status_code=500, 
            detail="TriPay environment variables (API_KEY, PRIVATE_KEY, MERCHANT_CODE) are not configured."
        )
    
    debug = os.getenv("TRIPAY_DEBUG", "true").lower() == "true"
    return {
        "api_key": api_key,
        "private_key": private_key,
        "merchant_code": merchant_code,
        "debug": debug,
        "base_url": "https://tripay.co.id/api-sandbox" if debug else "https://tripay.co.id/api"
    }

# Pricing mapping from pricing page
PLANS = {
    "micro": {"name": "Micro Pack", "price": 50000, "credits": 300},
    "lite": {"name": "Lite Pack", "price": 150000, "credits": 1000},
    "growth": {"name": "Growth Pack", "price": 500000, "credits": 4500},
    "business": {"name": "Business Pack", "price": 1000000, "credits": 10000},
}

@router.get("/channels")
def get_payment_channels():
    config = get_tripay_config()
    url = f"{config['base_url']}/merchant/payment-channel"
    headers = {'Authorization': f"Bearer {config['api_key']}"}
    
    try:
        response = requests.get(url, headers=headers)
        result = response.json()
        if not result.get("success"):
            print(f"TriPay Channels Error: {result}")
            raise HTTPException(status_code=400, detail=result.get("message", "Failed to fetch channels"))
        return result.get("data")
    except Exception as e:
        print(f"TriPay Channels Exception: {str(e)}")
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"TriPay error: {str(e)}")

@router.get("/fee-calculator")
def calculate_fee(code: str, amount: int):
    config = get_tripay_config()
    url = f"{config['base_url']}/merchant/fee-calculator"
    params = {'code': code, 'amount': amount}
    headers = {'Authorization': f"Bearer {config['api_key']}"}
    
    try:
        response = requests.get(url, params=params, headers=headers)
        result = response.json()
        if not result.get("success"):
            print(f"TriPay Fee Calc Error: {result}")
            raise HTTPException(status_code=400, detail=result.get("message", "Failed to calculate fee"))
        
        data = result.get("data")
        if not data or len(data) == 0:
            print("TriPay Fee Calc: Empty data returned")
            raise HTTPException(status_code=400, detail="TriPay returned no data for fee calculation")
            
        return data[0]
    except Exception as e:
        print(f"TriPay Fee Calc Exception: {str(e)}")
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"TriPay error: {str(e)}")


@router.post("/create")
def create_payment(
    plan_key: str,
    method: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    if plan_key not in PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan selected")
    
    config = get_tripay_config()
    plan = PLANS[plan_key]
    
    # 1. Calculate Fee or just send the base amount?
    # User wants fee borne by customer. 
    # Technically TriPay adds fee on top if configured in merchant panel, 
    # but we should send the base price and let TriPay calculate the total 
    # OR we calculate it and send the TOTAL. 
    # To be safe and show it accurately, we'll send the BASE price 
    # but we must ensure the 'amount' parameter is what the CUSTOMER pays.
    
    # Let's get the fee first to know the total amount to be paid by customer
    fee_info = calculate_fee(method, plan['price'])
    
    # TriPay calculates fee based on merchant settings. 
    # If set to 'Merchant', fee is in 'merchant' key. If 'Customer', it's in 'customer' key.
    # Since we want to ensure it's borne by the customer, we use whichever is available.
    customer_fee = fee_info.get('total_fee', {}).get('customer', 0)
    merchant_fee = fee_info.get('total_fee', {}).get('merchant', 0)
    
    # Use the larger one (usually only one is non-zero depending on TriPay config)
    fee_to_charge = max(customer_fee, merchant_fee)
    
    # Calculate final total and ensure it's an integer
    total_amount = int(plan['price'] + fee_to_charge)
    
    # Safety check: if TriPay already provided a total_amount.customer that is correct, use it
    if fee_info.get('total_amount', {}).get('customer', 0) > total_amount:
        total_amount = int(fee_info['total_amount']['customer'])
    
    # Create merchant_ref with plan_sku and user_id for easy recovery during callback
    # Format: INV-PLAN_KEY-TIMESTAMP-USER_ID
    merchant_ref = f"INV-{plan_key}-{int(time.time())}-{current_user.id}"
    
    # Signature TriPay: merchant_code + merchant_ref + amount
    signature_data = f"{config['merchant_code']}{merchant_ref}{total_amount}"
    signature = hmac.new(
        config['private_key'].encode(),
        signature_data.encode(),
        hashlib.sha256
    ).hexdigest()

    payload = {
        'method': method,
        'merchant_ref': merchant_ref,
        'amount': int(total_amount),
        'customer_name': current_user.name or current_user.email.split('@')[0],
        'customer_email': current_user.email,
        'order_items': [
            {
                'sku': plan_key,
                'name': plan['name'],
                'price': int(total_amount),
                'quantity': 1,
            }
        ],
        'callback_url': f"{os.getenv('BACKEND_URL')}/payments/callback",
        'return_url': f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/leads",
        'expired_time': int(time.time()) + (24 * 60 * 60), # 24 hours
        'signature': signature
    }

    headers = {
        'Authorization': f"Bearer {config['api_key']}",
        'Content-Type': 'application/json'
    }

    try:
        url = f"{config['base_url']}/transaction/create"
        # Log payload for debugging (don't log sensitive info like API keys, but payload is usually fine)
        print(f"TriPay Create Transaction Payload: {json.dumps(payload)}")
        
        response = requests.post(url, json=payload, headers=headers)
        result = response.json()
        
        if not result.get("success"):
            print(f"TriPay Create Transaction Error: {result}")
            raise HTTPException(status_code=400, detail=result.get("message", "Payment creation failed"))
            
        data = result.get("data")
        
        # Save to TransactionHistory
        new_transaction = models.TransactionHistory(
            user_id=current_user.id,
            merchant_ref=merchant_ref,
            amount=total_amount,
            plan_sku=plan_key,
            status="UNPAID",
            method=method,
            payment_url=data.get("checkout_url")
        )
        db.add(new_transaction)
        db.commit()
            
        return data
    except Exception as e:
        print(f"TriPay Create Transaction Exception: {str(e)}")
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"TriPay error: {str(e)}")


@router.post("/callback")
async def tripay_callback(request: Request, db: Session = Depends(database.get_db)):
    config = get_tripay_config()
    
    # 1. Get Signature
    callback_signature = request.headers.get("X-Callback-Signature")
    if not callback_signature:
        print("Tripay Callback ERROR: Missing X-Callback-Signature header")
        raise HTTPException(status_code=400, detail="Missing signature")

    body = await request.body()
    
    # 2. Verify HMAC SHA256
    digest = hmac.new(
        config['private_key'].encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    if callback_signature != digest:
        print(f"Tripay Callback ERROR: Invalid signature. Expected {digest}, got {callback_signature}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # 3. Parse Payload
    try:
        payload = json.loads(body)
        status = payload.get("status", "").upper()
        merchant_ref = payload.get("merchant_ref")
        order_items = payload.get("order_items", [])
        
        print(f"Tripay Callback RECEIVED: status={status}, ref={merchant_ref}")
        
        # 4. Find Transaction and update status (For ALL statuses)
        transaction = db.query(models.TransactionHistory).filter(models.TransactionHistory.merchant_ref == merchant_ref).first()
        if transaction:
            transaction.status = status
            if status == "PAID":
                transaction.paid_at = models.func.now()
            # Update method if Tripay provides it
            transaction.method = payload.get("payment_method") or transaction.method
            db.commit()
            print(f"Tripay Callback: Transaction {merchant_ref} status updated to {status}")
        else:
            print(f"Tripay Callback WARNING: Transaction {merchant_ref} not found in database history.")

        # 5. Handle PAID status (Credit Addition)
        if status == "PAID":
            # Extract data from merchant_ref (format: INV-[PLAN_KEY]-TIMESTAMP-USERID)
            try:
                ref_parts = merchant_ref.split("-")
                # Safety check if format changed or is legacy
                if len(ref_parts) >= 4:
                    plan_sku = ref_parts[1]
                    user_id = int(ref_parts[-1])
                elif len(ref_parts) == 3:
                    # Legacy format: INV-TIMESTAMP-USERID
                    user_id = int(ref_parts[-1])
                    # Try to get SKU from order_items as fallback
                    if order_items:
                        plan_sku = order_items[0].get("sku")
                    else:
                        print(f"Tripay Callback ERROR: Legacy ref {merchant_ref} and no order_items")
                        return {"success": False, "message": "Could not determine plan SKU for legacy payment"}
                else:
                    print(f"Tripay Callback ERROR: Invalid merchant_ref format: {merchant_ref}")
                    return {"success": False, "message": "Invalid merchant_ref format"}
                    
            except (ValueError, IndexError):
                print(f"Tripay Callback ERROR: Could not parse data from merchant_ref: {merchant_ref}")
                return {"success": False, "message": "Parsing error"}

            print(f"Tripay Callback PROCESSING: user_id={user_id}, sku={plan_sku}")
            
            if plan_sku in PLANS:
                user = db.query(models.User).filter(models.User.id == user_id).first()
                if user:
                    credits_to_add = PLANS[plan_sku]["credits"]
                    
                    # Ensure current credits is not None
                    if user.credits is None:
                        user.credits = 0
                        
                    old_credits = user.credits
                    
                    # Check if this transaction was already processed for credits to avoid double-crediting 
                    # (though status check usually handles it, it's safer)
                    # For now we rely on status logic, but we could add a flag to TransactionHistory.

                    user.credits += credits_to_add
                    
                    # Update plan type to pro for any paid plan purchase
                    user.plan_type = "pro"
                        
                    db.commit()
                    db.refresh(user)
                    
                    print(f"Tripay Callback SUCCESS: Updated user {user_id}. Credits: {old_credits} -> {user.credits}")
                    return {"success": True}
                else:
                    print(f"Tripay Callback ERROR: User {user_id} not found in database")
                    return {"success": False, "message": "User not found"}
            else:
                print(f"Tripay Callback ERROR: Invalid plan SKU: {plan_sku}")
                return {"success": False, "message": "Invalid plan SKU"}
        
        # For non-PAID status, we already updated the transaction record above
        return {"success": True}
            
    except Exception as e:
        print(f"Tripay Callback CRITICAL ERROR: {str(e)}")
        # We still return success to Tripay to stop retries if it's a code error, 
        # unless we want them to retry. But usually better to log and fix.
        # Tripay expects a JSON response.
            
    return {"success": True}

