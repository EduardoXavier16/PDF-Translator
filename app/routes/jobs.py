from pathlib import Path

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import UploadFile
from fastapi.responses import FileResponse

from app.services.jobs import JobService, OUTPUT_DIR


router = APIRouter()


@router.post("/jobs")
async def create_job(file: UploadFile) -> dict:
    job_service = JobService()
    job = await job_service.create_job_from_upload(file, "en", "pt-BR", "auto")
    return {"job_id": job.id, "status": job.status}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job_service = JobService()
    try:
        job = await job_service.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.id,
        "status": job.status,
        "total_elements": job.total_elements,
        "translated_elements": job.translated_elements,
        "current_stage": job.current_stage,
        "error": job.error,
    }


@router.get("/jobs/{job_id}/download")
async def download_job_result(job_id: str, format: str = "pdf") -> FileResponse:
    if format != "pdf":
        raise HTTPException(status_code=400, detail="Only pdf format is supported in the MVP")

    output_path = OUTPUT_DIR / f"{job_id}.pdf"
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Translated PDF not found")

    return FileResponse(
        path=output_path,
        media_type="application/pdf",
        filename=f"{job_id}.pdf",
    )


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict:
    job_service = JobService()
    try:
        job = await job_service.cancel_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc

    return {
        "job_id": job.id,
        "status": job.status,
        "total_elements": job.total_elements,
        "translated_elements": job.translated_elements,
        "current_stage": job.current_stage,
        "error": job.error,
    }
