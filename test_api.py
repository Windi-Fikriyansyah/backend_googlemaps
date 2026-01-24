import requests
import json

def test_search():
    url = "http://localhost:8000/leads/search"
    payload = {
        "keyword": "coffee shop",
        "location_name": "Jakarta, Indonesia",
        "radius": 1.0
    }
    
    print(f"Sending request to {url} with payload: {payload}")
    try:
        response = requests.post(url, json=payload)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            print("Response JSON:")
            print(json.dumps(response.json(), indent=2))
        else:
            print("Error:", response.text)
    except Exception as e:
        print(f"Failed to connect: {e}")
        print("Make sure the server is running (uvicorn main:app --reload) and database is accessible.")

if __name__ == "__main__":
    test_search()
