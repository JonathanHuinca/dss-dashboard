import uuid
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from app.core.security import get_current_user, require_role

router = APIRouter()


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_role("administrador")),
):
    job_id = str(uuid.uuid4())
    return {
        "job_id": job_id,
        "status": "queued",
        "filename": file.filename,
    }


@router.get("/{job_id}/status")
async def get_job_status(job_id: str, current_user: dict = Depends(get_current_user)):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Pendiente")


@router.get("/history")
async def get_ingestion_history(current_user: dict = Depends(get_current_user)):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Pendiente")
