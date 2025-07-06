from fastapi import APIRouter

router = APIRouter()

@router.get("/dashboard")
async def get_dashboard():
    return {"status": "ok"}