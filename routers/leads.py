from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import schemas, services, models, database

router = APIRouter(
    prefix="/leads",
    tags=["leads"]
)

@router.post("/search", response_model=schemas.SearchResponse)
def search_leads(request: schemas.SearchRequest, db: Session = Depends(database.get_db)):
    """
    Search for leads with Smart Hybrid Caching:
    1. Find all unique leads in DB for (keyword, location, radius).
    2. If DB has enough leads, return them immediately (0 API calls).
    3. If DB has some leads but not enough, fetch only the 'gap' from API.
    4. Link new leads to a new search record and return combined data.
    """
    # 1. Identify all unique leads already stored for this criteria across all searches
    # We use func.lower() for case-insensitive matching
    existing_leads_query = db.query(models.Lead).join(models.Lead.searches).filter(
        models.func.lower(models.Search.keyword) == request.keyword.lower(),
        models.func.lower(models.Search.location_name) == request.location_name.lower(),
        models.Search.radius == request.radius
    ).distinct()
    
    existing_leads = existing_leads_query.all()
    cached_count = len(existing_leads)

    if cached_count >= request.max_results:
        print(f"DEBUG: Smart Cache HIT (Full). Found {cached_count} leads, user asked for {request.max_results}.")
        return schemas.SearchResponse(
            search_id=0, # Virtual or last search ID
            keyword=request.keyword,
            location_name=request.location_name,
            total_results=request.max_results,
            leads=existing_leads[:request.max_results]
        )

    # 2. If we reach here, we need more data from the API
    print(f"DEBUG: Smart Cache PARTIAL. Found {cached_count} leads, user asked for {request.max_results}. Fetching gap...")
    
    # Geocoding
    lat, lng = services.get_coordinates(request.location_name)
    if lat is None or lng is None:
        raise HTTPException(status_code=400, detail="Could not geocode location name.")

    # Calculate starting page for API
    # If we have 20 leads, we assume page 1 is done. Start at page 2.
    start_page = (cached_count // 20) + 1
    gap = request.max_results - cached_count

    # Fetch ONLY what's missing
    new_places = services.search_google_maps(
        keyword=request.keyword,
        lat=lat,
        lng=lng,
        radius_km=request.radius,
        max_results=gap,
        start_page=start_page
    )
    
    # 3. Create a new search record for this request
    new_search = models.Search(
        user_id=1, 
        keyword=request.keyword,
        location_name=request.location_name,
        radius=request.radius,
        max_results=request.max_results
    )
    db.add(new_search)
    db.commit()
    db.refresh(new_search)

    # 4. Link existing leads to this new search (so they're part of this history)
    for lead in existing_leads:
        if lead not in new_search.leads:
            new_search.leads.append(lead)
    
    # 5. Process and Save NEW leads from the API
    final_new_leads = services.process_and_save_leads(db, new_search, new_places)
    
    db.commit()
    db.refresh(new_search)

    return schemas.SearchResponse(
        search_id=new_search.id,
        keyword=request.keyword,
        location_name=request.location_name,
        total_results=len(new_search.leads),
        leads=new_search.leads
    )
