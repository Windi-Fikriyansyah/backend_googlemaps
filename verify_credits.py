import requests
import json
import time

BACKEND_URL = "http://localhost:8000"

# Note: We assume user_id=1 exists and has some credits.
# If not, you should log in first or seed the DB.

def get_user_credits():
    # Helper to check credits (using a mock/easy way or checking DB via direct API if authorized)
    # Since we don't have a direct credit check API without auth here, 
    # we'll assume the logs will show the deduction or we can check via a mock search.
    pass

def test_search_credit_deduction():
    print("\n--- Testing Search Credit Deduction ---")
    url = f"{BACKEND_URL}/leads/search"
    payload = {
        "keyword": "cafe",
        "location_name": "Jakarta",
        "radius": 1.0,
        "max_results": 5
    }
    
    print(f"Sending search request (max_results: 5)...")
    try:
        response = requests.post(url, json=payload)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            num_leads = len(data.get("leads", []))
            print(f"Success! Found {num_leads} leads.")
            print("Check backend logs for 'Deducted X credits' message.")
        elif response.status_code == 403:
            print("Forbidden: Likely insufficient credits (this is a valid test case if credits are 0).")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")

def test_whatsapp_credit_deduction():
    print("\n--- Testing WhatsApp Webhook Credit Deduction ---")
    url = f"{BACKEND_URL}/whatsapp/webhook"
    
    # First, we'd need a message ID in history. 
    # For testing, let's assume one exists or mock the processing.
    # In reality, we'd call /broadcast first.
    
    # Mocking a webhook for an existing message (msg_id must exist in your DB)
    # Replace '12345' with a real ID from your message_histories table if you want a real test.
    payload = {
        "id": "msg_test_123", # Mock ID
        "status": "sent",
        "state": "delivered"
    }
    
    print(f"Sending mock WhatsApp webhook for status 'sent'...")
    try:
        response = requests.post(url, json=payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        print("Note: If 'msg_test_123' doesn't exist, no credit will be deducted (expected).")
        print("Check backend logs for 'Deducted 1 credit' message if ID was real.")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_search_credit_deduction()
    test_whatsapp_credit_deduction()
