import requests
import json

def test_webhook():
    url = "http://localhost:8000/whatsapp/webhook"
    
    # Mock payload from Fonnte
    payload = {
        "device": "628123456789",
        "id": "12345", # Ensure this ID exists in your MessageHistory or use a real one
        "stateid": "state_123",
        "status": "sent",
        "state": "delivered"
    }
    
    print(f"Sending mock webhook to {url}...")
    try:
        response = requests.post(url, json=payload)
        print(f"Status Code: {response.status_code}")
        print("Response:", response.json())
    except Exception as e:
        print(f"Connection failed: {e}")
        print("Make sure the backend server is running on port 8000.")

if __name__ == "__main__":
    test_webhook()
