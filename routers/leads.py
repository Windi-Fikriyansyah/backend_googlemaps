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

    # Credit check removed as requested
    
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

        num_results = len(leads_with_saved_status)
        # Credit deduction removed as requested

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
    try:
        new_places = services.search_google_maps(
            keyword=request.keyword,
            lat=lat,
            lng=lng,
            radius_km=request.radius,
            max_results=gap,
            start_page=start_page,
            api_key=current_user.search_api_key if current_user else None
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
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

    num_results = len(leads_with_saved_status)
    # Credit deduction removed as requested

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
    
    # Check if already saved
    existing = db.query(models.SavedLead).filter(
        models.SavedLead.user_id == current_user.id,
        models.SavedLead.lead_id == request.lead_id
    ).first()

    if not existing:
        new_saved = models.SavedLead(
            user_id=current_user.id,
            lead_id=request.lead_id,
            category=request.category or "General"
        )
        db.add(new_saved)
        db.commit()
    else:
        # Update category if already exists?
        existing.category = request.category or "General"
        db.commit()

    return {"message": "Lead saved successfully"}

@router.delete("/save/{lead_id}")
def unsave_lead(
    lead_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    saved_entry = db.query(models.SavedLead).filter(
        models.SavedLead.user_id == current_user.id,
        models.SavedLead.lead_id == lead_id
    ).first()

    if not saved_entry:
        raise HTTPException(status_code=404, detail="Saved lead not found")
    
    db.delete(saved_entry)
    db.commit()
    return {"message": "Lead removed from saved"}

@router.post("/save-batch")
def save_leads_batch(
    request: schemas.LeadSaveBatchRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    count = 0
    for lead_id in request.lead_ids:
        # Check if already saved
        existing = db.query(models.SavedLead).filter(
            models.SavedLead.user_id == current_user.id,
            models.SavedLead.lead_id == lead_id
        ).first()

        if not existing:
            new_saved = models.SavedLead(
                user_id=current_user.id,
                lead_id=lead_id,
                category=request.category or "General"
            )
            db.add(new_saved)
            count += 1
        else:
            existing.category = request.category or "General"
            
    if count > 0 or len(request.lead_ids) > 0:
        db.commit()
    
    return {"message": f"{count} new leads saved successfully"}

@router.get("/saved", response_model=List[schemas.LeadResponse])
def get_saved_leads(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user_strict)
):
    # Simply return the relationship data
    # We map it to ensure the is_saved field is True
    leads = []
    for saved in current_user.saved_leads_assoc:
        lead_data = schemas.LeadResponse.model_validate(saved.lead)
        lead_data.category = saved.category # USE THE SAVED CATEGORY INSTEAD OF ORIGINAL
        lead_data.is_saved = True
        leads.append(lead_data)
    return leads
