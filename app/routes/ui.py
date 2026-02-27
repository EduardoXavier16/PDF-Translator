from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.jobs import JobService, MAX_PAGES_TO_TRANSLATE


router = APIRouter()


def get_job_service() -> JobService:
    return JobService()


@router.get("/", response_class=HTMLResponse)
async def upload_page(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        "upload.html",
        {"request": request},
    )


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_status_page(
    request: Request,
    job_id: str,
    job_service: JobService = Depends(get_job_service),
) -> HTMLResponse:
    try:
        job = await job_service.get_job(job_id)
    except KeyError:
        return request.app.state.templates.TemplateResponse(
            "job_status.html",
            {
                "request": request,
                "job": {
                    "id": job_id,
                    "status": "not_found",
                    "total_elements": 0,
                    "translated_elements": 0,
                    "current_stage": "not_found",
                    "error": "Job not found",
                },
            },
            status_code=404,
        )

    return request.app.state.templates.TemplateResponse(
        "job_status.html",
        {"request": request, "job": job},
    )


@router.post("/jobs", response_class=HTMLResponse)
async def create_job_redirect(
    request: Request,
    job_service: JobService = Depends(get_job_service),
) -> HTMLResponse:
    form = await request.form()
    file = form.get("file")
    source_lang = form.get("source_lang") or "en"
    target_lang = form.get("target_lang") or "pt-BR"
    strategy = form.get("strategy") or "auto"

    start_page_raw = form.get("start_page")
    end_page_raw = form.get("end_page")

    start_page = 1
    end_page = MAX_PAGES_TO_TRANSLATE

    if isinstance(start_page_raw, str):
        try:
            parsed_start = int(start_page_raw)
            if parsed_start > 0:
                start_page = parsed_start
        except ValueError:
            start_page = 1

    if isinstance(end_page_raw, str):
        try:
            parsed_end = int(end_page_raw)
            if parsed_end >= start_page:
                end_page = parsed_end
        except ValueError:
            end_page = MAX_PAGES_TO_TRANSLATE

    job = await job_service.create_job_from_upload(
        file=file,
        source_lang=source_lang,
        target_lang=target_lang,
        strategy=strategy,
        start_page=start_page,
        end_page=end_page,
    )
    return request.app.state.templates.TemplateResponse(
        "upload.html",
        {
            "request": request,
            "job": job,
        },
    )
