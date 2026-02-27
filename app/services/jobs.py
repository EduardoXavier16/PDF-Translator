import asyncio
import html as html_stdlib
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import UploadFile
from fpdf import FPDF
from fpdf.errors import FPDFException
from pypdf import PdfReader

from app.services.models import JobModel
from app.services.translation_llm_client import TranslationClient


JOBS: Dict[str, JobModel] = {}

BASE_STORAGE_DIR = Path("storage")
ORIGINAL_DIR = BASE_STORAGE_DIR / "original"
OUTPUT_DIR = BASE_STORAGE_DIR / "output"

MAX_PAGES_TO_TRANSLATE = 10
MAX_CONCURRENT_TRANSLATIONS = 2


def _normalize_long_tokens(text: str) -> str:
    cleaned_lines: List[str] = []
    for raw_line in text.splitlines():
        tokens = raw_line.split(" ")
        normalized_tokens: List[str] = []
        for token in tokens:
            if len(token) > 80:
                parts: List[str] = []
                start_index = 0
                while start_index < len(token):
                    end_index = start_index + 40
                    parts.append(token[start_index:end_index])
                    start_index = end_index
                normalized_tokens.append(" ".join(parts))
            else:
                normalized_tokens.append(token)
        cleaned_lines.append(" ".join(normalized_tokens))
    return "\n".join(cleaned_lines)


def _sanitize_text_for_pdf(text: str) -> str:
    cleaned_characters: List[str] = []
    allowed_control = {"\n", "\r", "\t"}

    for character in text:
        code_point = ord(character)
        if code_point < 32 and character not in allowed_control:
            continue

        if code_point > 255:
            if character in ("–", "—", "−"):
                cleaned_characters.append("-")
                continue
            if character in ("“", "”", "„", "‟"):
                cleaned_characters.append('"')
                continue
            if character in ("‘", "’", "‚", "‛"):
                cleaned_characters.append("'")
                continue

            cleaned_characters.append("?")
            continue

        cleaned_characters.append(character)

    return "".join(cleaned_characters)


class JobService:
    async def create_job_from_upload(
        self,
        file: UploadFile,
        source_lang: str,
        target_lang: str,
        strategy: str,
        start_page: Optional[int] = None,
        end_page: Optional[int] = None,
    ) -> JobModel:
        ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        job_id = uuid4().hex
        original_path = ORIGINAL_DIR / f"{job_id}.pdf"
        output_path = OUTPUT_DIR / f"{job_id}.pdf"

        file_bytes = await file.read()
        original_path.write_bytes(file_bytes)

        job = JobModel(
            id=job_id,
            status="pending",
            total_elements=0,
            translated_elements=0,
            current_stage="queued",
            source_lang=source_lang,
            target_lang=target_lang,
            error=None,
        )
        JOBS[job_id] = job

        asyncio.create_task(
            self._run_translation_job(
                job_id=job_id,
                original_path=original_path,
                output_path=output_path,
                start_page=start_page,
                end_page=end_page,
            )
        )

        return job

    async def _run_translation_job(
        self,
        job_id: str,
        original_path: Path,
        output_path: Path,
        start_page: Optional[int],
        end_page: Optional[int],
    ) -> None:
        job = JOBS.get(job_id)
        if job is None:
            return

        try:
            job.current_stage = "extract_text"

            pages_text: List[str] = []
            reader = PdfReader(str(original_path))
            total_pages = len(reader.pages)

            safe_start_page = 1 if start_page is None or start_page <= 0 else start_page
            safe_end_page = end_page if end_page is not None and end_page >= safe_start_page else (
                safe_start_page + MAX_PAGES_TO_TRANSLATE - 1
            )

            max_end_by_window = safe_start_page + MAX_PAGES_TO_TRANSLATE - 1
            if safe_end_page > max_end_by_window:
                safe_end_page = max_end_by_window

            if safe_start_page > total_pages:
                safe_start_page = total_pages

            if safe_end_page > total_pages:
                safe_end_page = total_pages

            start_index = safe_start_page - 1
            end_index = safe_end_page - 1

            for index, page in enumerate(reader.pages):
                if index < start_index:
                    continue
                if index > end_index:
                    break
                text = page.extract_text()
                if text is None:
                    continue
                stripped = text.strip()
                if not stripped:
                    continue
                pages_text.append(stripped)

            total_elements = len(pages_text)
            job.total_elements = total_elements

            if job.status == "cancelled":
                job.current_stage = "cancelled"
                return

            if total_elements == 0:
                output_path.write_bytes(original_path.read_bytes())
                job.status = "completed"
                job.current_stage = "completed"
                return

            job.current_stage = "translate"

            client = TranslationClient()
            translated_pages: List[str] = [""] * total_elements
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_TRANSLATIONS)

            source_lang = job.source_lang
            target_lang = job.target_lang

            async def translate_page(index: int, content: str) -> None:
                if job.status == "cancelled":
                    return

                async with semaphore:
                    if job.status == "cancelled":
                        return

                    translated = await client.translate(
                        text=content,
                        source_lang=source_lang,
                        target_lang=target_lang,
                    )

                if job.status == "cancelled":
                    return

                translated_pages[index] = translated
                job.translated_elements += 1

            translate_tasks = [
                asyncio.create_task(translate_page(index=index, content=page_text))
                for index, page_text in enumerate(pages_text)
            ]
            await asyncio.gather(*translate_tasks)

            if job.status == "cancelled":
                job.current_stage = "cancelled"
                return

            job.current_stage = "render_pdf"

            pdf = FPDF()
            pdf.set_auto_page_break(auto=True, margin=15)
            pdf.set_margins(left=15, top=15, right=15)

            for translated_page in translated_pages:
                pdf.add_page()
                pdf.set_font("Arial", size=11)
                safe_text = _sanitize_text_for_pdf(translated_page)
                try:
                    pdf.multi_cell(0, 5, safe_text)
                except FPDFException:
                    normalized = _normalize_long_tokens(safe_text)
                    try:
                        pdf.multi_cell(0, 5, normalized)
                    except FPDFException:
                        continue

            pdf.output(str(output_path))

            job.status = "completed"
            job.current_stage = "completed"
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.current_stage = "failed"
            job.error = str(exc)

    async def get_job(self, job_id: str) -> JobModel:
        job = JOBS.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    async def cancel_job(self, job_id: str) -> JobModel:
        job = JOBS.get(job_id)
        if job is None:
            raise KeyError(job_id)

        if job.status in {"completed", "failed", "cancelled"}:
            return job

        job.status = "cancelled"
        job.current_stage = "cancelled"
        return job
