from fastapi import APIRouter, Request, HTTPException

router = APIRouter()

@router.post("/analytics/event")
async def analytics_event(request: Request):
    consent = request.cookies.get("analytics_consent")
    if consent != "granted":
        raise HTTPException(status_code=403, detail="Consent required for analytics")
    # process event...