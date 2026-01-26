from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import schemas, services, models, database
from routers.auth import get_current_user, get_current_user_strict
from typing import Optional, List

router = APIRouter(
    prefix="/leads",
    tags=["leads"]
)

@router.post("/search", response_model=schemas.SearchResponse)
def search_leads(
    request: schemas.SearchRequest, 
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(get_current_user)
):
    """
    Search for leads with Smart Hybrid Caching.
    If not logged in, it uses user_id=1 as a fallback for search history.
    """
    # 0. Handle guest or invalid session
    if not current_user:
        # If no user, we use admin (id=1) but maybe we should enforce login for searching if credits are involved?
        # For now, let's keep the user_id=1 fallback but check credits if it's a real user.
        user_id = 1
        user = db.query(models.User).filter(models.User.id == 1).first()
    else:
        user_id = current_user.id
        user = current_user

    # 0.1 Check if user has ANY credits
    if user.credits <= 0:
        raise HTTPException(
            status_code=403, 
            detail="Insufficient credits. Please top up your account."
        )
    
    # 1. Identify all unique leads already stored for this criteria
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
        
        saved_lead_ids = {l.id for l in current_user.saved_leads} if current_user else set()
        leads_with_saved_status = []
        for lead in existing_leads[:request.max_results]:
            lead_dict = {
                "id": lead.id,
                "google_place_id": lead.google_place_id,
                "name": lead.name,
                "address": lead.address,
                "phone": lead.phone,
                "website": lead.website,
                "rating": lead.rating,
                "category": lead.category,
                "is_saved": lead.id in saved_lead_ids
            }
            leads_with_saved_status.append(lead_dict)

        # Deduct credits for cached results
        num_results = len(leads_with_saved_status)
        user.credits = max(0, user.credits - num_results)
        db.commit()
        db.refresh(user)

        return schemas.SearchResponse(
            search_id=0, # Virtual or last search ID
            keyword=request.keyword,
            location_name=request.location_name,
            total_results=num_results,
            leads=leads_with_saved_status
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
        user_id=user_id, 
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

    # Create response with is_saved status
    saved_lead_ids = {l.id for l in current_user.saved_leads} if current_user else set()
    leads_with_saved_status = []
    for lead in (existing_leads[:request.max_results] if cached_count >= request.max_results else new_search.leads):
        lead_dict = {
            "id": lead.id,
            "google_place_id": lead.google_place_id,
            "name": lead.name,
            "address": lead.address,
            "phone": lead.phone,
            "website": lead.website,
            "rating": lead.rating,
            "category": lead.category,
            "is_saved": lead.id in saved_lead_ids
        }
        leads_with_saved_status.append(lead_dict)

    # Deduct credits for new/combined results
    num_results = len(leads_with_saved_status)
    user.credits = max(0, user.credits - num_results)
    db.commit()
    db.refresh(user)

    return schemas.SearchResponse(
        search_id=new_search.id if cached_count < request.max_results else 0,
        keyword=request.keyword,
        location_name=request.location_name,
        total_results=num_results,
        leads=leads_with_saved_status
    )

@router.post("/save")
def save_lead(
    request: schemas.LeadSaveRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    lead = db.query(models.Lead).filter(models.Lead.id == request.lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    if lead not in current_user.saved_leads:
        current_user.saved_leads.append(lead)
        db.commit()
    
    return {"message": "Lead saved successfully"}

@router.post("/save-batch")
def save_leads_batch(
    request: schemas.LeadSaveBatchRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    leads = db.query(models.Lead).filter(models.Lead.id.in_(request.lead_ids)).all()
    
    count = 0
    for lead in leads:
        if lead not in current_user.saved_leads:
            current_user.saved_leads.append(lead)
            count += 1
            
    if count > 0:
        db.commit()
    
    return {"message": f"{count} leads saved successfully"}

@router.get("/saved", response_model=List[schemas.LeadResponse])
def get_saved_leads(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    # Simply return the relationship data
    # We map it to ensure the is_saved field is True
    leads = []
    for lead in current_user.saved_leads:
        lead_dict = schemas.LeadResponse.model_validate(lead)
        lead_dict.is_saved = True
        leads.append(lead_dict)
    return leads
