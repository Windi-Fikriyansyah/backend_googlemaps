from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
import models, database
import os, time, requests, json, uuid
from pydantic import BaseModel
from passlib.context import CryptContext

# Security
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(prefix="/payments/linkbayar", tags=["linkbayar"])

# Pricing
PLANS = {
    "premium": {"name": "Wamaps Premium", "price": 500, "credits": 999999},
}

class CreatePaymentRequest(BaseModel):
    plan_key: str
    customer_name: str
    customer_email: str
    payment_method: str

@router.get("/methods")
def get_payment_methods():
    api_key = os.getenv("LINKBAYAR_API_KEY")
    url = "https://app.linkbayar.my.id/api/get_metode_pembayaran"
    headers = {"X-API-Key": api_key or "api_key_anda"}
    
    try:
        response = requests.get(url, headers=headers)
        return response.json()
    except Exception as e:
        print(f"LinkBayar Get Methods ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch payment methods")

@router.post("/create")
def create_linkbayar_payment(
    req: CreatePaymentRequest,
    db: Session = Depends(database.get_db)
):
    if req.plan_key not in PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan selected")
    
    plan = PLANS[req.plan_key]
    api_key = os.getenv("LINKBAYAR_API_KEY")
    project = os.getenv("LINKBAYAR_PROJECT_NAME")
    
    # Generate unique merchant_ref / order_id
    u_id = str(uuid.uuid4().hex)
    order_id = f"INV-{int(time.time())}-{u_id[:4]}"
    
    # LinkBayar Create Transaction API
    # method is now dynamic from request
    method = req.payment_method or "qris" 
    url = f"https://app.linkbayar.my.id/api/transactioncreate/{method}"
    
    payload = {
        "project": project or "WAMAPS",
        "order_id": order_id,
        "amount": int(plan["price"])
    }
    
    headers = {
        "X-API-Key": api_key or "api_key_anda",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        result = response.json()
        
        if "payment" not in result:
            print(f"LinkBayar Create ERROR: {result}")
            raise HTTPException(status_code=400, detail=result.get("message", "Payment creation failed"))
        
        payment_data = result["payment"]
        
        # Save to database
        existing_user = db.query(models.User).filter(models.User.email == req.customer_email).first()
        
        new_transaction = models.TransactionHistory(
            user_id=existing_user.id if existing_user else None,
            merchant_ref=order_id,
            amount=int(payment_data.get("total_payment", plan["price"])),
            plan_sku=req.plan_key,
            status="UNPAID",
            method=method,
            payment_url=payment_data.get("payment_url"), # LinkBayar might return a URL for VA/Retail
            customer_name=req.customer_name,
            customer_email=req.customer_email
        )
        
        db.add(new_transaction)
        db.commit()
        
        return {
            "order_id": order_id,
            "payment_number": payment_data.get("payment_number"),
            "total_payment": payment_data.get("total_payment"),
            "fee": payment_data.get("fee"),
            "payment_url": payment_data.get("payment_url"),
            "plan_name": plan["name"]
        }
        
    except Exception as e:
        print(f"LinkBayar Create Transaction Exception: {str(e)}")
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"LinkBayar error: {str(e)}")

@router.post("/webhook")
async def linkbayar_webhook(request: Request, db: Session = Depends(database.get_db)):
    try:
        payload = await request.json()
        print(f"LinkBayar Webhook RECEIVED: {json.dumps(payload)}")
        
        order_id = payload.get("order_id")
        status = payload.get("status") # 'success' or 'expired'
        
        if status != "success":
            print(f"LinkBayar Webhook: Status {status} for {order_id}. Updating as EXPIRED.")
            transaction = db.query(models.TransactionHistory).filter(models.TransactionHistory.merchant_ref == order_id).first()
            if transaction:
                transaction.status = "EXPIRED"
                db.commit()
            return {"message": "Ignored"}
        
        transaction = db.query(models.TransactionHistory).filter(models.TransactionHistory.merchant_ref == order_id).first()
        if not transaction:
            print(f"LinkBayar Webhook ERROR: Transaction {order_id} not found")
            return {"message": "Transaction Not Found"}
            
        if transaction.status == "PAID":
            return {"message": "Already Paid"}
            
        # Update transaction
        transaction.status = "PAID"
        transaction.paid_at = func.now()
        
        # Process User & Credits
        email = transaction.customer_email
        name = transaction.customer_name
        plan_sku = transaction.plan_sku
        
        # Ensure it's an int
        plan_info = PLANS.get(plan_sku, {"credits": 0})
        credits_to_add = int(plan_info.get("credits", 0))
        
        user = db.query(models.User).filter(models.User.email == email).first()
        temp_password = None
        
        if not user:
            # Create new user
            u_id = str(uuid.uuid4().hex)
            temp_password = u_id[:8]
            hashed_password = pwd_context.hash(temp_password)
            
            user = models.User(
                email=email,
                name=name,
                password_hash=hashed_password,
                plan_type="pro",
                credits=credits_to_add
            )
            db.add(user)
            db.flush() # Get user.id
            transaction.user_id = user.id
            print(f"LINKBAYAR WEBHOOK: Created new user {email} with temp pass {temp_password}")
        else:
            # Update existing user
            current_credits = user.credits if user.credits is not None else 0
            user.credits = current_credits + credits_to_add
            user.plan_type = "pro"
            if not user.name:
                user.name = name
            transaction.user_id = user.id
            print(f"LINKBAYAR WEBHOOK: Updated existing user {email}. Added {credits_to_add} credits.")
            
        db.commit()
        
        # Sent email via Brevo
        subject = "Akses Premium Wamaps - Akun Anda Telah Aktif!"
        if temp_password:
             # New User
             html = f"""
             <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #eee; border-radius: 20px;">
                <h2 style="color: #2563eb; margin-bottom: 20px;">Halo {name},</h2>
                <p style="font-size: 16px; line-height: 1.5;">Terima kasih telah berlangganan <b>Wamaps Premium</b>!</p>
                <p style="font-size: 16px; line-height: 1.5;">Pembayaran Anda telah berhasil diterima dan akses akun Anda sudah aktif seumur hidup.</p>
                
                <div style="background: #f8fafc; padding: 20px; border-radius: 15px; margin: 25px 0; border: 1px solid #e2e8f0;">
                    <p style="margin: 0; font-size: 14px; color: #64748b; font-weight: bold; text-transform: uppercase; letter-spacing: 1px;">Detail Login Anda:</p>
                    <p style="margin: 15px 0 5px 0; font-size: 16px;"><b>Email:</b> {email}</p>
                    <p style="margin: 0; font-size: 16px;"><b>Password:</b> <span style="background: #eff6ff; color: #1d4ed8; padding: 4px 8px; border-radius: 6px; font-family: monospace; font-weight: bold;">{temp_password}</span></p>
                </div>
                
                <p style="font-size: 16px; line-height: 1.5;">Silakan login di dashboard kami melalui tombol di bawah ini:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="https://wamaps.myxyzz.online/login" style="display: inline-block; background: #2563eb; color: white; padding: 16px 32px; border-radius: 12px; text-decoration: none; font-weight: bold; font-size: 18px; box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.2);">Login ke Dashboard</a>
                </div>
                
                <p style="margin-top: 40px; font-size: 12px; color: #94a3b8; border-top: 1px solid #f1f5f9; pt: 20px;">
                    *Harap segera ganti password Anda setelah login pertama kali demi keamanan akun Anda.<br>
                    Jika Anda tidak merasa melakukan transaksi ini, silakan hubungi tim support kami.
                </p>
             </div>
             """
             send_email_brevo(email, subject, html)
        else:
             # Existing User
             html = f"""
             <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #eee; border-radius: 20px;">
                <h2 style="color: #2563eb; margin-bottom: 20px;">Halo {name},</h2>
                <p style="font-size: 16px; line-height: 1.5;">Terima kasih atas pembelian Anda!</p>
                <p style="font-size: 16px; line-height: 1.5;">Akses <b>Wamaps Premium</b> Anda telah berhasil diaktifkan/diperbarui.</p>
                
                <p style="font-size: 16px; line-height: 1.5; margin-top: 20px;">Anda dapat menggunakan email dan password yang sudah Anda buat sebelumnya untuk login ke sistem.</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="https://wamaps.myxyzz.online/login" style="display: inline-block; background: #2563eb; color: white; padding: 16px 32px; border-radius: 12px; text-decoration: none; font-weight: bold; font-size: 18px;">Masuk ke Dashboard</a>
                </div>
             </div>
             """
             send_email_brevo(email, subject, html)
             
        return {"message": "Success"}
        
    except Exception as e:
        print(f"LinkBayar Webhook CRITICAL ERROR: {str(e)}")
        return {"message": "Internal Error"}

@router.get("/status/{merchant_ref}")
def check_payment_status(merchant_ref: str, db: Session = Depends(database.get_db)):
    transaction = db.query(models.TransactionHistory).filter(models.TransactionHistory.merchant_ref == merchant_ref).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    return {
        "status": transaction.status,
        "paid_at": transaction.paid_at,
        "plan": transaction.plan_sku
    }

def send_email_brevo(to_email: str, subject: str, html_content: str):
    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "no-reply@wamaps.online")
    sender_name = os.getenv("BREVO_SENDER_NAME", "Wamaps Official")
    
    if not api_key:
        print("BREVO_API_KEY not configured. Skipping real email sending.")
        return False
        
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }
    
    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if 200 <= response.status_code < 300:
            print(f"Brevo EMAIL SENT to {to_email}")
            return True
        else:
            print(f"Brevo EMAIL ERROR: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"Brevo EMAIL EXCEPTION: {str(e)}")
        return False
