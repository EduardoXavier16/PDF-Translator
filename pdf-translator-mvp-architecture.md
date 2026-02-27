## PDF Translator Service — MVP Architecture

### 1. Scope and Goals

- Input (MVP): single PDF file, primarily English source text.
- Output (MVP): translated PDF in Brazilian Portuguese (pt-BR).
- Processing: fully asynchronous, resilient to long-running jobs, suitable for 700+ page PDFs.
- Target environment: CPU-only machine (Ryzen 5 5600G, 32 GB RAM), no GPU.
- LLM: local model running in Docker, accessed via HTTP from the Python backend.

Out of scope for this MVP:

- EPUB input/output (planned for a later phase).
- Pixel-perfect layout reproduction for complex multi-column or table-heavy PDFs.
- Image text translation inside embedded figures.

This document is aligned with the original PRD `PDF Book Translator (LLM)` and focuses on a Python-only backend.

### 2. High-Level Architecture

- API layer: FastAPI application exposing HTTP endpoints.
- Background processing: Celery workers with Redis as broker and result backend (or Redis as broker + Postgres for persistence).
- Storage:
  - Object storage (local filesystem or S3-compatible, e.g. MinIO) for original and translated PDFs.
  - Postgres database for jobs, elements, and translations metadata.
- LLM integration:
  - HTTP client in Python that talks to a local LLM container.
  - The LLM is used strictly as a translation engine with deterministic prompts.

Main components:

1. API service (FastAPI).
2. Worker service (Celery workers).
3. Storage (filesystem or S3-compatible).
4. Postgres database.
5. Local LLM container.

The API node enqueues jobs; workers consume jobs, call the LLM, generate the translated PDF, and update the database.

### 3. API Design (MVP)

#### 3.1 Endpoints

**POST `/jobs`**

- Purpose: create a translation job from an uploaded PDF.
- Request:
  - `file`: PDF file (multipart/form-data).
  - `source_lang`: optional, default `"en"`.
  - `target_lang`: optional, default `"pt-BR"`.
  - `strategy`: `"auto" | "fast" | "hi_res" | "ocr_only"` (default `"auto"`).
  - `output_format`: `"pdf"` (MVP).
- Response:
  - HTTP 202 Accepted.
  - JSON body:
    - `job_id: string`
    - `status: "pending" | "queued" | "running" | "completed" | "failed"`

**GET `/jobs/{job_id}`**

- Purpose: retrieve status and progress of a job.
- Response:
  - `job_id: string`
  - `status: "pending" | "queued" | "partitioning" | "translating" | "rendering" | "completed" | "failed"`
  - `created_at: string`
  - `finished_at: string | null`
  - `current_stage: string`
  - `total_elements: number`
  - `translated_elements: number`
  - `error: string | null`

**GET `/jobs/{job_id}/download?format=pdf`**

- Purpose: download the translated PDF.
- Behaviors:
  - If `status !== "completed"`, respond with 409 or 404 and a structured error JSON.
  - If successful, stream the generated PDF as `application/pdf`.

### 4. Data Model

Database: Postgres.

#### 4.1 `jobs` table

- `id` (UUID, primary key).
- `status` (string): `"pending" | "queued" | "partitioning" | "translating" | "rendering" | "completed" | "failed"`.
- `source_lang` (string, e.g. `"en"`).
- `target_lang` (string, e.g. `"pt-BR"`).
- `strategy` (string): `"auto" | "fast" | "hi_res" | "ocr_only"`.
- `output_formats` (string array, MVP: always `["pdf"]`).
- `total_elements` (integer, default 0).
- `translated_elements` (integer, default 0).
- `created_at` (timestamp).
- `finished_at` (timestamp, nullable).
- `error` (text, nullable).

#### 4.2 `elements` table

- `id` (bigint, primary key).
- `job_id` (UUID, foreign key to `jobs.id`).
- `element_id` (string, unique per job if using `unique_element_ids=True`).
- `type` (string, e.g. `"Title"`, `"NarrativeText"`, `"ListItem"`, `"Table"`).
- `text` (text).
- `metadata_json` (JSONB):
  - `page_number`
  - bounding box
  - other details from Unstructured.
- `order_index` (integer, ensures deterministic ordering for reconstruction).
- `page_number` (integer, denormalized from metadata for faster queries).

#### 4.3 `translations` table

- `id` (bigint, primary key).
- `job_id` (UUID, foreign key to `jobs.id`).
- `element_id` (string, references `elements.element_id`).
- `source_text` (text).
- `translated_text` (text, nullable while in progress).
- `status` (string): `"pending" | "in_progress" | "ok" | "failed" | "suspicious"`.
- `model` (string): model name used by the LLM container.
- `prompt_version` (string): version ID for the translation prompt.
- `retry_count` (integer).
- `created_at` (timestamp).
- `updated_at` (timestamp).

### 5. Processing Pipeline

The core pipeline is implemented as a Celery workflow, driven by a single entrypoint task `process_job(job_id)` that calls smaller steps.

#### 5.1 Steps Overview

1. **Ingest**
   - Save PDF file to storage (`original/{job_id}.pdf`).
   - Create job record with status `queued`.
2. **Partition**
   - Run `unstructured.partition_pdf` using the configured strategy.
   - Create `elements` records for each element with `text`.
   - Update `jobs.total_elements`.
   - Set job status to `translating`.
3. **Translate elements**
   - For each element with text, create or update a `translations` record.
   - Call the LLM container to translate the text.
   - Store the translated text and mark status as `ok` or `suspicious`.
   - Increment `translated_elements` on the job.
4. **Render PDF**
   - Fetch all translated elements in `order_index` order.
   - Build an HTML document that preserves structure (headings, paragraphs, lists, tables).
   - Render HTML to PDF via Playwright or WeasyPrint.
   - Save the translated PDF to storage (`output/{job_id}.pdf`).
   - Update job status to `completed`.
5. **Finalize**
   - Set `finished_at`.
   - If any step fails, set job `status = "failed"` and fill `error`.

#### 5.2 Partitioning Details

- Library: `unstructured` with `partition_pdf`.
- Parameters:
  - `strategy`: `"fast"`, `"hi_res"`, or `"ocr_only"` depending on user choice and auto-detection.
  - `include_page_breaks=True`.
  - `unique_element_ids=True` to ensure deterministic `element_id` values.
- Each Unstructured element is converted into a row in `elements`.
- Optional grouping rules:
  - MVP: one element per translation unit.
  - Later: group small fragments per page if fragmentation becomes problematic.

#### 5.3 Translation Details and Anti-Hallucination

- For each element with `text`:
  - Build a prompt:
    - Translate faithfully from English to Brazilian Portuguese.
    - Do not add or remove information.
    - Preserve all numbers, units, acronyms, and technical terms where possible.
    - If the text is illegible or incomplete, return a short marker indicating this, without inventing content.
- Anti-hallucination heuristics:
  - If `source_text` contains several numeric tokens, check that these numbers appear in `translated_text`.
  - For very short elements (1–3 characters), prefer:
    - Echoing the original text, or
    - Returning an “illegible” marker, never a full sentence.
- Suspicious translations:
  - If heuristics fail, set translation status to `"suspicious"` and optionally requeue for another attempt or human review.

### 6. LLM Integration (Dedicated TranslateGemma 4B Container)

#### 6.1 Requirements and Constraints

- CPU-only environment:
  - Ryzen 5 5600G.
  - 32 GB RAM.
  - No GPU available.
- Implications:
  - Use a translation-focused model optimized for CPU.
  - Keep the LLM service isolated from other applications and containers.

#### 6.2 Chosen Model: TranslateGemma 4B

- Model: `translategemma` (4B variant), from the Ollama model library [translategemma][1].
- Purpose:
  - Specialized for translation between many languages, including English and Portuguese.
  - Designed to act as a professional translator only, not a general chat model.
- Prompt pattern (high level):
  - Instruct the model to:
    - Translate from English (en) to Brazilian Portuguese (pt-BR).
    - Preserve numbers, units, acronyms, and technical terms.
    - Return only the translated text with no explanations.

#### 6.3 Dedicated LLM Container

- The existing LLM container used by other applications (e.g. `OdontoDent-ollama`) is not modified.
- This project uses a **separate container** running an Ollama server dedicated to TranslateGemma:
  - Example container name: `pdf-translator-llm`.
  - Example port mapping: host `11534` → container `11434`.
  - Example volume: `pdf-translator-llm:/root/.ollama` (isolated model storage).
- Base URL for this service (from the perspective of the Python backend):
  - `http://localhost:11534`

#### 6.4 HTTP Client Contract

The Python backend encapsulates LLM calls behind a small client:

- Function signature:
  - `translate_text(text: str, source_lang: str, target_lang: str) -> str`
- Responsibilities:
  - Construct the translation prompt according to the rules in section 5.3.
  - Send a POST request to the dedicated LLM container (TranslateGemma 4B).
  - Handle timeouts and network errors.
  - Parse and validate the response, extracting only the translated text.
  - Raise explicit exceptions on failure so that the worker can retry or mark the element as failed.

Configuration parameters (environment variables):

- `TRANSLATION_LLM_BASE_URL` (e.g. `http://localhost:11534`).
- `TRANSLATION_LLM_MODEL_NAME` (e.g. `translategemma`).
- Request and response timeouts.

#### 6.5 Operational Checklist (TranslateGemma Container)

- Create and start the dedicated LLM container (one-time setup):

```bash
docker run -d \
  --name pdf-translator-llm \
  -p 11534:11434 \
  -v pdf-translator-llm:/root/.ollama \
  ollama/ollama:latest
```

- Start the container (after reboot or when stopped):

```bash
docker start pdf-translator-llm
```

- Stop the container (to free CPU/RAM when not using the translator service):

```bash
docker stop pdf-translator-llm
```

- Pull the TranslateGemma model inside the container:

```bash
docker exec -it pdf-translator-llm ollama pull translategemma
```

- Backend environment variables checklist:
  - `TRANSLATION_LLM_BASE_URL` set to `http://localhost:11534`.
  - `TRANSLATION_LLM_MODEL_NAME` set to `translategemma`.
  - Optional:
    - `TRANSLATION_LLM_REQUEST_TIMEOUT_SECONDS` (e.g. `60`).
    - `TRANSLATION_LLM_MAX_RETRIES` (e.g. `3`).

### 7. Rendering Pipeline (HTML → PDF)

- Input:
  - Ordered list of translated elements with type and metadata.
- HTML generation:
  - Titles (`Title`, `Heading`) → `<h1>`, `<h2>`, `<h3>` according to hierarchy or font size metadata.
  - Narrative text → `<p>`.
  - Lists → `<ul>`, `<ol>`, `<li>`.
  - Tables:
    - Use `text_as_html` from Unstructured when available.
    - Translate cell contents while preserving `<table>`, `<tr>`, `<td>` structure.
- CSS:
  - Page margins and fonts.
  - Optional header text such as “Translated by PDF Translator Service”.
  - Page numbering where supported by the renderer.
- PDF renderer:
  - Choose between:
    - Playwright (Chromium headless) for high fidelity, or
    - WeasyPrint for pure Python rendering.
- Output:
  - Single PDF stored in `output/{job_id}.pdf`.

### 8. Non-Functional Requirements (MVP)

- Scalability:
  - Jobs processed by multiple worker processes.
  - Retry logic for individual element translations.
- Resilience:
  - Checkpoints at each stage (partitioned, translating, rendering).
  - Ability to resume jobs after worker or process restarts.
- Observability:
  - Structured logs for each stage (ingest, partition, translation, render).
  - Basic metrics:
    - Average elements per minute.
    - Average translation latency per element.
- Security:
  - Configurable limits on:
    - PDF size (e.g. up to 500 MB).
    - Page count (e.g. up to 1,000 pages).
  - Optional antivirus scan hooks before processing.
  - No data sent to external APIs in the MVP, all processing remains local.

### 9. Web UI (Python)

The user interface is implemented entirely in Python, using FastAPI and simple HTML templates (e.g. Jinja2 or Starlette templates). No separate JavaScript frontend framework is required for the MVP.

#### 9.1 Pages

- **Home / Upload page** (`GET /`):
  - Simple HTML form:
    - File input for PDF upload.
    - Select for source language (default `English (en)`).
    - Select for target language (default `Portuguese (pt-BR)`).
    - Select for extraction strategy:
      - `auto`, `fast`, `hi_res`, `ocr_only`.
    - Submit button “Send for translation”.
  - On submit:
    - Form posts to `POST /jobs` (multipart).
    - Backend creates the job and redirects to `/jobs/{job_id}`.

- **Job status page** (`GET /jobs/{job_id}`):
  - Displays:
    - Job ID.
    - Source and target languages.
    - Current status:
      - `pending`, `partitioning`, `translating`, `rendering`, `completed`, `failed`.
    - Progress:
      - `translated_elements` of `total_elements`.
    - Current stage description (e.g. “Translating elements…”).
    - Error message if status is `failed`.
  - Actions:
    - “Refresh status” button or automatic refresh using a simple HTML meta refresh or lightweight JavaScript polling.
    - When job is `completed`, a “Download translated PDF” button links to `GET /jobs/{job_id}/download?format=pdf`.

- **(Optional) Jobs list page** (`GET /jobs`):
  - Simple table of recent jobs:
    - Job ID.
    - Original file name.
    - Status.
    - Created/finished timestamps.
    - Link to `/jobs/{job_id}` for details.

#### 9.2 Implementation Notes

- The same FastAPI application that exposes the JSON endpoints also serves the HTML pages.
- Templates:
  - Use a small set of Jinja2 templates:
    - `upload.html` for the home page.
    - `job_status.html` for job details.
    - `jobs_list.html` if the optional list page is implemented.
- Styling:
  - Minimal CSS for layout and readability.
  - Focus on clarity and practicality rather than complex design.

### 10. Future Extensions

Planned but out of scope for the first MVP:

- Additional input formats: EPUB, DOCX, TXT, and others supported by Unstructured.
- EPUB output generation using `ebooklib` or equivalent.
- More advanced auto-strategy selection:
  - Start with `fast` text extraction.
  - Fallback to `hi_res` or `ocr_only` when text quality is poor.
- Richer Web UI with more advanced front-end features.
- Fine-grained retry tools for:
  - Re-translating specific elements marked as failed or suspicious.
  - Manual correction loops for high-value content.

