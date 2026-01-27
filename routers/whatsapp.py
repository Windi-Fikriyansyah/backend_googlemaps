from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import models, schemas, database
from routers.auth import get_current_user_strict
from typing import List
import requests
import os
import random
import time
from fastapi import BackgroundTasks
import database

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

FONNTE_TOKEN = os.getenv("FONNTE_TOKEN", "REPLACE_WITH_YOUR_FONNTE_TOKEN")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

@router.get("/templates", response_model=List[schemas.MessageTemplateResponse])
def get_templates(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    return db.query(models.MessageTemplate).filter(models.MessageTemplate.user_id == current_user.id).all()

@router.post("/templates", response_model=schemas.MessageTemplateResponse)
def create_template(
    template: schemas.MessageTemplateCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    new_template = models.MessageTemplate(
        **template.model_dump(),
        user_id=current_user.id
    )
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    return new_template

@router.put("/templates/{template_id}", response_model=schemas.MessageTemplateResponse)
def update_template(
    template_id: int,
    template_data: schemas.MessageTemplateCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    template = db.query(models.MessageTemplate).filter(
        models.MessageTemplate.id == template_id,
        models.MessageTemplate.user_id == current_user.id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
        
    for key, value in template_data.model_dump().items():
        setattr(template, key, value)
        
    db.commit()
    db.refresh(template)
    return template

@router.delete("/templates/{template_id}")
def delete_template(
    template_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    template = db.query(models.MessageTemplate).filter(
        models.MessageTemplate.id == template_id,
        models.MessageTemplate.user_id == current_user.id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
        
    db.delete(template)
    db.commit()
    return {"message": "Template deleted successfully"}

def process_broadcast_background(
    lead_ids: List[int],
    message_content: str,
    device_token: str,
    user_id: int,
    delay: int
):
    """
    Background task to send messages with safe delays and batching.
    - 30-60s random delay between messages.
    - 15 min rest after every 20 messages.
    """
    db = database.SessionLocal()
    try:
        leads = db.query(models.Lead).filter(models.Lead.id.in_(lead_ids)).all()
        if not leads:
            return

        # --- NEW: Number Validation Step ---
        print(f"DEBUG [Broadcast User {user_id}]: Starting number validation for {len(leads)} leads...")
        
        registered_numbers = set()
        all_normalized_numbers = {} # phone -> lead_id mapping for reverse lookup if needed
        
        # 1. Normalize all numbers
        for lead in leads:
            if lead.phone:
                phone = lead.phone.replace(" ", "").replace("+", "").replace("-", "")
                if phone.startswith("08"):
                    phone = "628" + phone[2:]
                all_normalized_numbers[phone] = lead.id

        # 2. Batch validate in groups of 500
        phone_list = list(all_normalized_numbers.keys())
        for i in range(0, len(phone_list), 500):
            batch = phone_list[i:i+500]
            try:
                validate_url = "https://api.fonnte.com/validate"
                validate_payload = {'target': ",".join(batch)}
                validate_headers = {'Authorization': device_token}
                
                resp = requests.post(validate_url, data=validate_payload, headers=validate_headers)
                val_result = resp.json()
                
                if val_result.get("status"):
                    # Add all registered numbers to our set
                    registered_in_batch = val_result.get("registered", [])
                    registered_numbers.update(registered_in_batch)
                    print(f"DEBUG [Broadcast User {user_id}]: Validated batch {i//500 + 1}. Registered: {len(registered_in_batch)}/{len(batch)}")
                else:
                    print(f"ERROR [Broadcast User {user_id}]: Validation API failed: {val_result.get('reason')}")
                    # If validation fails, we might want to fail the whole thing or assume all are unregistered?
                    # Let's assume all are unregistered to be safe if it explicitly fails.
            except Exception as e:
                print(f"ERROR [Broadcast User {user_id}]: Exception during validation: {str(e)}")

        print(f"DEBUG [Broadcast User {user_id}]: Validation complete. Total registered: {len(registered_numbers)}")
        # --- End of Validation Step ---

        sent_count = 0
        batch_limit = 20

        for i, lead in enumerate(leads):
            if not lead.phone:
                continue

            # Check if number is registered
            phone = lead.phone.replace(" ", "").replace("+", "").replace("-", "")
            if phone.startswith("08"):
                phone = "628" + phone[2:]
            
            if phone not in registered_numbers:
                print(f"DEBUG [Broadcast User {user_id}]: Skipping unregistered number {phone} (Lead ID: {lead.id})")
                continue

            # 1. Safe Delay (Random 30-60s)
            # Skip delay for the very first message ever sent in this task
            if sent_count > 0:
                # Batch rest: if we just finished 20 messages
                if sent_count % batch_limit == 0:
                    print(f"DEBUG [Broadcast User {user_id}]: Batch limit reached ({batch_limit}). Resting for 15 minutes...")
                    time.sleep(900) # 15 minutes
                else:
                    sleep_time = random.randint(30, 60)
                    print(f"DEBUG [Broadcast User {user_id}]: Waiting {sleep_time}s before next message...")
                    time.sleep(sleep_time)

            # 2. Personalize Message
            personalized_message = message_content
            placeholders = {
                "{{name}}": lead.name or "",
                "{{address}}": lead.address or "",
                "{{phone}}": lead.phone or "",
                "{{category}}": lead.category or ""
            }
            
            for placeholder, value in placeholders.items():
                if placeholder in personalized_message:
                    personalized_message = personalized_message.replace(placeholder, str(value))

            # 3. Send to Fonnte
            url = "https://api.fonnte.com/send"
            payload = {
                'target': phone,
                'message': personalized_message,
                'countryCode': '62',
                'delay': delay, # Original delay from request (per-batch delay in Fonnte if they use it)
            }
            headers = {'Authorization': device_token}

            try:
                response = requests.post(url, data=payload, headers=headers)
                result = response.json()
                
                if result.get("status"):
                    message_id = result.get("id", [None])[0] if isinstance(result.get("id"), list) else result.get("id")
                    if message_id:
                        new_history = models.MessageHistory(
                            id=str(message_id),
                            user_id=user_id,
                            target=phone,
                            message=personalized_message,
                            status=result.get("process", "processing")
                        )
                        db.add(new_history)
                        db.commit()
                        sent_count += 1
                        print(f"DEBUG [Broadcast User {user_id}]: Sent to {phone} (Internal ID: {lead.id})")
                else:
                    print(f"ERROR [Broadcast User {user_id}]: Fonnte failed for {phone}: {result.get('reason')}")
            except Exception as e:
                print(f"ERROR [Broadcast User {user_id}]: Exception for {phone}: {str(e)}")

    finally:
        db.close()
        print(f"DEBUG [Broadcast User {user_id}]: Task finished. Total sent: {sent_count}")

@router.post("/broadcast")
def send_broadcast(
    request: schemas.BroadcastRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    # 0. Check if user has ANY credits
    if current_user.credits <= 0:
        raise HTTPException(
            status_code=403, 
            detail="Insufficient credits. Please top up your account to send messages."
        )

    # 1. Get Device Token
    device_token = ""
    if request.device_id:
        device = db.query(models.WhatsAppDevice).filter(
            models.WhatsAppDevice.id == request.device_id,
            models.WhatsAppDevice.user_id == current_user.id
        ).first()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        device_token = device.token
    else:
        # Fallback to first connected device
        device = db.query(models.WhatsAppDevice).filter(
            models.WhatsAppDevice.user_id == current_user.id,
            models.WhatsAppDevice.status == "connected"
        ).first()
        if not device:
            raise HTTPException(status_code=400, detail="No connected device found. Please connect a device first.")
        device_token = device.token

    if not device_token:
        raise HTTPException(status_code=400, detail="Device token not found")

    # 2. Validate leads exist
    leads_count = db.query(models.Lead).filter(models.Lead.id.in_(request.lead_ids)).count()
    if leads_count == 0:
        raise HTTPException(status_code=404, detail="No leads found")
        
    # 3. Get message content
    message_content = ""
    if request.template_id:
        template = db.query(models.MessageTemplate).filter(
            models.MessageTemplate.id == request.template_id,
            models.MessageTemplate.user_id == current_user.id
        ).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        message_content = template.content
    elif request.custom_content:
        message_content = request.custom_content
    else:
        raise HTTPException(status_code=400, detail="Template or custom content is required")
        
    # 4. Start Background Task
    background_tasks.add_task(
        process_broadcast_background,
        lead_ids=request.lead_ids,
        message_content=message_content,
        device_token=device_token,
        user_id=current_user.id,
        delay=request.delay or 3
    )

    return {
        "message": "Broadcast started in background. Messages will be sent gradually with safe delays to prevent spam detection.",
        "targets_count": leads_count,
        "mode": "background",
        "batch_info": "20 messages per batch, 15 minutes rest between batches, 30-60s delay per message."
    }


@router.get("/history", response_model=List[schemas.MessageHistoryResponse])
def get_message_history(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    return db.query(models.MessageHistory).filter(
        models.MessageHistory.user_id == current_user.id
    ).order_by(models.MessageHistory.created_at.desc()).all()


@router.post("/webhook")
async def fonnte_webhook(
    request: Request,
    db: Session = Depends(database.get_db)
):
    """
    Webhook endpoint for Fonnte. Receives incoming messages and status updates.
    Uses raw request body to avoid 422 validation errors from varying payload formats.
    """
    try:
        # Try to parse as JSON first
        try:
            payload = await request.json()
        except:
            # If not JSON, try form data
            form = await request.form()
            payload = dict(form)
        
        msg_id = payload.get("id")
        stateid = payload.get("stateid")
        status = payload.get("status")
        state = payload.get("state")
        
        if not msg_id:
            # Some webhook calls might be state-only
            if stateid:
                db.query(models.MessageHistory).filter(
                    models.MessageHistory.stateid == stateid
                ).update({"state": state})
                db.commit()
            return {"status": "ok"}

        # Find the message by ID
        message = db.query(models.MessageHistory).filter(
            models.MessageHistory.id == str(msg_id)
        ).first()
        
        if message:
            # Check for SENT status to deduct credit
            if status == "sent" and not message.credits_deducted:
                user = db.query(models.User).filter(models.User.id == message.user_id).first()
                if user:
                    user.credits = max(0, user.credits - 1)
                    message.credits_deducted = True
                    print(f"DEBUG: Deducted 1 credit from user {user.id} for message {message.id}")

            if status:
                message.status = status
            if state:
                message.state = state
            if stateid:
                message.stateid = stateid
            db.commit()
        
        return {"status": "ok"}
    except Exception as e:
        # Log error but still return ok to prevent Fonnte from retrying
        print(f"Webhook error: {str(e)}")
        return {"status": "ok"}


@router.post("/webhook-connect")
def fonnte_webhook_connect(
    payload: schemas.FonnteConnectPayload,
    db: Session = Depends(database.get_db)
):
    """
    Endpoint yang akan dipanggil oleh Fonnte saat device connect/disconnect.
    Saat device connect, otomatis update semua webhook URLs.
    """
    device_number = payload.device
    connection_status = payload.status  # "connect" or "disconnect"
    
    # Find device by device_number
    device = db.query(models.WhatsAppDevice).filter(
        models.WhatsAppDevice.device_number == device_number
    ).first()
    
    if device:
        # Update device status in database
        if connection_status == "connect":
            device.status = "connected"
            
            # Auto-update webhook URLs when device connects
            webhook_url = f"{BACKEND_URL}/whatsapp/webhook"
            webhook_payload = {
                'name': device.name,
                'webhook': webhook_url,
                'webhookconnect': f"{BACKEND_URL}/whatsapp/webhook-connect",
                'webhookstatus': webhook_url,
            }
            webhook_headers = {'Authorization': device.token}
            try:
                requests.post("https://api.fonnte.com/update-device", data=webhook_payload, headers=webhook_headers)
            except:
                pass
                
        elif connection_status == "disconnect":
            device.status = "disconnected"
            
        db.commit()
    
    return {"status": "ok"}


@router.post("/refresh-status")
def refresh_message_status(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    """
    Fetch and update status for all pending/processing messages from Fonnte API.
    This is an alternative to webhook - user can manually refresh status.
    """
    # Get user's device token
    device = db.query(models.WhatsAppDevice).filter(
        models.WhatsAppDevice.user_id == current_user.id
    ).first()
    
    if not device or not device.token:
        raise HTTPException(status_code=400, detail="No device found. Please add a device first.")
    
    # Get all messages that are not in final state (sent, invalid, expired, etc.)
    # Include all possible non-final statuses
    non_final_statuses = [
        "pending", "processing", "waiting", "process", "queued",
        "Pending", "Processing", "Waiting", "Process", "Queued"
    ]
    pending_messages = db.query(models.MessageHistory).filter(
        models.MessageHistory.user_id == current_user.id,
        models.MessageHistory.status.in_(non_final_statuses)
    ).all()
    
    # Debug: Also get all messages to see what statuses exist
    all_messages = db.query(models.MessageHistory).filter(
        models.MessageHistory.user_id == current_user.id
    ).all()
    all_statuses = list(set([m.status for m in all_messages]))
    
    updated_count = 0
    errors = []
    fonnte_responses = []  # Debug: track all responses
    
    for msg in pending_messages:
        try:
            # Call Fonnte API to check status
            url = "https://api.fonnte.com/status"
            payload = {"id": msg.id}
            headers = {"Authorization": device.token}
            
            response = requests.post(url, data=payload, headers=headers)
            result = response.json()
            
            # Debug: save raw response
            fonnte_responses.append({
                "message_id": msg.id,
                "fonnte_response": result,
                "current_db_status": msg.status
            })
            
            if result.get("status"):
                new_status = result.get("message_status", msg.status)
                if new_status and new_status != msg.status:
                    # Deduct credit if status becomes "sent"
                    if new_status == "sent" and not msg.credits_deducted:
                        user = db.query(models.User).filter(models.User.id == msg.user_id).first()
                        if user:
                            user.credits = max(0, user.credits - 1)
                            msg.credits_deducted = True
                            print(f"DEBUG: Deducted 1 credit from user {user.id} for message {msg.id} via refresh")
                    
                    msg.status = new_status
                    updated_count += 1
        except Exception as e:
            errors.append(f"Error checking ID {msg.id}: {str(e)}")
    
    db.commit()
    
    return {
        "message": f"Status refresh complete. Updated {updated_count} messages.",
        "updated_count": updated_count,
        "checked_count": len(pending_messages),
        "all_statuses_in_db": all_statuses,
        "fonnte_responses": fonnte_responses,
        "errors": errors if errors else None
    }


# --- WhatsApp Device Management ---

@router.get("/devices", response_model=List[schemas.WhatsAppDeviceResponse])
def get_devices(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    return db.query(models.WhatsAppDevice).filter(models.WhatsAppDevice.user_id == current_user.id).all()

@router.post("/devices", response_model=schemas.WhatsAppDeviceResponse)
def create_device(
    device_data: schemas.WhatsAppDeviceCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    # Call Fonnte API to add device
    # Clean phone number
    clean_device = device_data.device.replace(" ", "").replace("+", "").replace("-", "")
    if clean_device.startswith("08"):
        clean_device = "628" + clean_device[2:]
        
    # Call Fonnte API to add device
    url = "https://api.fonnte.com/add-device"
    payload = {
        'name': device_data.name,
        'device': clean_device,
        'autoread': 'false',
        'personal': 'false',
        'group': 'false'
    }
    headers = {
        'Authorization': FONNTE_TOKEN # Account token from env
    }
    
    try:
        response = requests.post(url, data=payload, headers=headers)
        result = response.json()
        
        if not result.get("status"):
            raise HTTPException(
                status_code=400, 
                detail=f"Fonnte creation failed: {result.get('reason', 'Unknown error')}"
            )
            
        # Create new device in local DB with Fonnte's generated token
        new_device = models.WhatsAppDevice(
            name=device_data.name,
            device_number=clean_device,
            token=result.get("token"),
            user_id=current_user.id
        )
        db.add(new_device)
        db.commit()
        db.refresh(new_device)
        
        # Auto-update webhook URL for the newly created device
        webhook_url = f"{BACKEND_URL}/whatsapp/webhook"
        webhook_payload = {
            'name': device_data.name,
            'webhook': webhook_url,
            'webhookconnect': f"{BACKEND_URL}/whatsapp/webhook-connect",
            'webhookstatus': webhook_url,
        }
        webhook_headers = {'Authorization': result.get("token")}
        try:
            requests.post("https://api.fonnte.com/update-device", data=webhook_payload, headers=webhook_headers)
        except:
            pass  # Ignore webhook update errors during creation
        
        return new_device
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Fonnte API error: {str(e)}")

@router.put("/devices/{device_id}", response_model=schemas.WhatsAppDeviceResponse)
def update_device(
    device_id: int,
    device_data: schemas.WhatsAppDeviceUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    device = db.query(models.WhatsAppDevice).filter(
        models.WhatsAppDevice.id == device_id,
        models.WhatsAppDevice.user_id == current_user.id
    ).first()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    # Clean current device number
    clean_device = device.device_number.replace(" ", "").replace("+", "").replace("-", "")
    if clean_device.startswith("08"):
        clean_device = "628" + clean_device[2:]
        
    # Call Fonnte API to update device
    url = "https://api.fonnte.com/update-device"
    payload = {
        'name': device_data.name if device_data.name else device.name,
        'device': clean_device,
    }
    headers = {
        'Authorization': device.token # Use device token
    }
    
    try:
        response = requests.post(url, data=payload, headers=headers)
        result = response.json()
        
        if not result.get("status"):
            raise HTTPException(
                status_code=400, 
                detail=f"Fonnte update failed: {result.get('reason', 'Unknown error')}"
            )
            
        # Update local DB
        for key, value in device_data.model_dump(exclude_unset=True).items():
            setattr(device, key, value)
        
        device.device_number = clean_device # Ensure cleaned number is saved
            
        db.commit()
        db.refresh(device)
        return device
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Fonnte API error: {str(e)}")

@router.delete("/devices/{device_id}")
def delete_device(
    device_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    device = db.query(models.WhatsAppDevice).filter(
        models.WhatsAppDevice.id == device_id,
        models.WhatsAppDevice.user_id == current_user.id
    ).first()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    db.delete(device)
    db.commit()
    return {"message": "Device deleted successfully from local database"}

# --- Fonnte Device Integration ---

@router.get("/devices/{device_id}/qr")
def get_device_qr(
    device_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    device = db.query(models.WhatsAppDevice).filter(
        models.WhatsAppDevice.id == device_id,
        models.WhatsAppDevice.user_id == current_user.id
    ).first()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    url = "https://api.fonnte.com/qr"
    headers = {'Authorization': device.token}
    
    try:
        response = requests.post(url, headers=headers)
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fonnte QR error: {str(e)}")

@router.post("/devices/{device_id}/reconnect")
def reconnect_device(
    device_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    device = db.query(models.WhatsAppDevice).filter(
        models.WhatsAppDevice.id == device_id,
        models.WhatsAppDevice.user_id == current_user.id
    ).first()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    url = "https://api.fonnte.com/reconnect"
    headers = {'Authorization': device.token}
    
    try:
        response = requests.post(url, headers=headers)
        result = response.json()
        
        # Auto-update webhook URL after reconnect
        webhook_url = f"{BACKEND_URL}/whatsapp/webhook"
        webhook_payload = {
            'name': device.name,
            'webhook': webhook_url,
            'webhookconnect': f"{BACKEND_URL}/whatsapp/webhook-connect",
            'webhookstatus': webhook_url,
        }
        webhook_headers = {'Authorization': device.token}
        webhook_result = None
        try:
            webhook_response = requests.post("https://api.fonnte.com/update-device", data=webhook_payload, headers=webhook_headers)
            webhook_result = webhook_response.json()
        except:
            pass
        
        return {
            **result,
            "webhook_updated": webhook_result.get("status", False) if webhook_result else False,
            "webhook_url": webhook_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fonnte Reconnect error: {str(e)}")

@router.post("/devices/{device_id}/disconnect")
def disconnect_device(
    device_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    device = db.query(models.WhatsAppDevice).filter(
        models.WhatsAppDevice.id == device_id,
        models.WhatsAppDevice.user_id == current_user.id
    ).first()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    url = "https://api.fonnte.com/disconnect"
    headers = {'Authorization': device.token}
    
    try:
        response = requests.post(url, headers=headers)
        result = response.json()
        
        # Update local status if successful or already disconnected
        if result.get("status") or result.get("detail") == "device already disconnected":
            device.status = "disconnected"
            db.commit()
            
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fonnte Disconnect error: {str(e)}")

@router.get("/devices/{device_id}/status")
def get_device_status(
    device_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    device = db.query(models.WhatsAppDevice).filter(
        models.WhatsAppDevice.id == device_id,
        models.WhatsAppDevice.user_id == current_user.id
    ).first()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    url = "https://api.fonnte.com/device"
    headers = {'Authorization': device.token}
    
    try:
        response = requests.post(url, headers=headers)
        result = response.json()
        
        webhook_updated = False
        
        # Update local status if available in response
        if result.get("status"):
            # Fonnte status might be boolean or string, let's normalize
            new_status = "connected" if result.get("device_status") == "connect" else "disconnected"
            device.status = new_status
            db.commit()
            
            # Auto-update webhook when device is connected
            if new_status == "connected":
                webhook_url = f"{BACKEND_URL}/whatsapp/webhook"
                webhook_payload = {
                    'name': device.name,
                    'webhook': webhook_url,
                    'webhookconnect': f"{BACKEND_URL}/whatsapp/webhook-connect",
                    'webhookstatus': webhook_url,
                }
                webhook_headers = {'Authorization': device.token}
                try:
                    webhook_response = requests.post("https://api.fonnte.com/update-device", data=webhook_payload, headers=webhook_headers)
                    webhook_result = webhook_response.json()
                    webhook_updated = webhook_result.get("status", False)
                except:
                    pass
        
        return {
            **result,
            "webhook_updated": webhook_updated,
            "webhook_url": f"{BACKEND_URL}/whatsapp/webhook" if webhook_updated else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fonnte Status error: {str(e)}")


# --- Auto Webhook URL Update ---

def update_device_webhook(device_token: str, device_name: str):
    """
    Helper function to update webhook URL for a single device.
    This constructs the webhook URL from BACKEND_URL and updates Fonnte.
    """
    webhook_url = f"{BACKEND_URL}/whatsapp/webhook"
    
    url = "https://api.fonnte.com/update-device"
    payload = {
        'name': device_name,
        'webhook': webhook_url,
        'webhookconnect': webhook_url,
        'webhookstatus': webhook_url,
    }
    headers = {
        'Authorization': device_token
    }
    
    try:
        response = requests.post(url, data=payload, headers=headers)
        return response.json()
    except Exception as e:
        return {"status": False, "reason": str(e)}


@router.post("/devices/{device_id}/update-webhook")
def update_single_device_webhook(
    device_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    """
    Update webhook URL for a specific device.
    The webhook URL will be automatically constructed from BACKEND_URL environment variable.
    """
    device = db.query(models.WhatsAppDevice).filter(
        models.WhatsAppDevice.id == device_id,
        models.WhatsAppDevice.user_id == current_user.id
    ).first()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    result = update_device_webhook(device.token, device.name)
    
    if not result.get("status"):
        raise HTTPException(
            status_code=400,
            detail=f"Failed to update webhook: {result.get('reason', 'Unknown error')}"
        )
    
    return {
        "message": "Webhook URL updated successfully",
        "webhook_url": f"{BACKEND_URL}/whatsapp/webhook",
        "fonnte_response": result
    }


@router.post("/update-all-webhooks")
def update_all_device_webhooks(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    """
    Update webhook URL for ALL devices owned by the current user.
    This is useful for one-time setup or when BACKEND_URL changes.
    """
    devices = db.query(models.WhatsAppDevice).filter(
        models.WhatsAppDevice.user_id == current_user.id
    ).all()
    
    if not devices:
        raise HTTPException(status_code=404, detail="No devices found")
    
    results = []
    success_count = 0
    failed_count = 0
    webhook_url = f"{BACKEND_URL}/whatsapp/webhook"
    
    for device in devices:
        result = update_device_webhook(device.token, device.name)
        results.append({
            "device_id": device.id,
            "device_name": device.name,
            "success": result.get("status", False),
            "response": result
        })
        
        if result.get("status"):
            success_count += 1
        else:
            failed_count += 1
    
    return {
        "message": f"Webhook update completed. Success: {success_count}, Failed: {failed_count}",
        "webhook_url": webhook_url,
        "results": results
    }

