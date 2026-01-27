import requests
from geopy.geocoders import Nominatim
from sqlalchemy.orm import Session
import models, schemas
import os
import time

# Initialize SearchAPI.io configuration
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY") # User should set this in .env
SEARCH_API_URL = "https://www.searchapi.io/api/v1/search"

geolocator = Nominatim(user_agent="WAMaps_LeadGenerator_v1.0", timeout=10)

def get_coordinates(location_name: str):
    """
    Convert location name to coordinates using Geopy.
    """
    try:
        location = geolocator.geocode(location_name)
        if location:
            return location.latitude, location.longitude
        return None, None
    except Exception as e:
        print(f"Geocoding error: {e}")
        return None, None

def search_google_maps(keyword: str, lat: float, lng: float, radius_km: float, max_results: int = 20, start_page: int = 1):
    """
    Search Google Maps places nearby using SearchAPI.io.
    Fetches results starting from 'start_page' until 'max_results' total are found (or no more results).
    Prevents duplicates in the result list.
    """
    if not SEARCH_API_KEY:
        raise Exception("SEARCH_API_KEY not configured in .env.")

    all_results = []
    seen_ids = set()
    radius_meters = int(radius_km * 1000)
    
    # ll parameter format: @latitude,longitude,radius_meters
    ll_param = f"@{lat},{lng},{radius_meters}m"
    
    # Calculate how many pages we need to fetch starting from start_page
    # If we already have some results (start_page > 1), we still fetch until we hit max_results
    # or until we've fetched enough pages to cover the gap.
    
    current_page = start_page
    while len(all_results) < max_results:
        params = {
            "engine": "google_maps",
            "q": keyword,
            "ll": ll_param,
            "api_key": SEARCH_API_KEY,
            "page": current_page
        }
        
        try:
            print(f"DEBUG: Fetching SearchAPI page {current_page} for query: {keyword}")
            response = requests.get(SEARCH_API_URL, params=params)
            response.raise_for_status()
            data = response.json()
            
            local_results = data.get("local_results", [])
            if not local_results:
                print(f"DEBUG: No more results from SearchAPI at page {current_page}")
                break
                
            for place in local_results:
                place_id = place.get("data_id") or place.get("place_id")
                if place_id and place_id not in seen_ids:
                    seen_ids.add(place_id)
                    all_results.append(place)
                    
                if len(all_results) >= max_results:
                    break
            
            if len(local_results) < 20:
                break
            
            current_page += 1
            # Safety cap to prevent infinite loops or excessive API calls
            if current_page > start_page + 5: 
                break
                
        except Exception as e:
            print(f"Error fetching from SearchAPI (page={current_page}): {e}")
            break
            
    return all_results

def process_and_save_leads(db: Session, search_record: models.Search, places: list):
    all_results = []
    
    for place in places:
        google_place_id = place.get("data_id") or place.get("place_id")
        
        if not google_place_id:
            continue

        # Check if Lead (Business) already exists globally
        lead = db.query(models.Lead).filter(models.Lead.google_place_id == google_place_id).first()
        
        if not lead:
            # Create new lead record
            lead = models.Lead(
                google_place_id=google_place_id,
                name=place.get("title", "Unknown"),
                address=place.get("address", "N/A"),
                phone=place.get("phone"),
                website=place.get("website"),
                rating=place.get("rating"),
                category=place.get("type") or (place.get("types", [None])[0] if place.get("types") else None)
            )
            db.add(lead)
            db.commit()
            db.refresh(lead)
            print(f"DEBUG: Saved NEW lead: {lead.name}")

        # Link Lead to this specific Search (Association)
        # Check if already linked to avoid errors
        if lead not in search_record.leads:
            search_record.leads.append(lead)
            db.add(search_record)
            db.commit()
            db.refresh(search_record)
            print(f"DEBUG: Linked lead '{lead.name}' to Search ID {search_record.id}")

        all_results.append(lead)
        
    return all_results
