## PDF Translator (Desktop-first, Windows 11)

PDF Translator is a local-first PDF translation tool written in Python.  
It is designed to run as a **desktop-style app on Windows 11**, using:

- FastAPI + Jinja2 templates for the backend/UI.
- A local or remote LLM (e.g. Translategemma) for translation.
- A dark, Windows-11-like UI embedded in a WebView (planned via `pywebview`).

The app focuses on:

- Translating PDFs between supported languages (initially English, Portuguese (pt-BR), Spanish, French, German, Italian).
- Working **entirely on the user’s machine** (no cloud backend required).
- Providing a single-window experience: upload, progress tracking, and automatic download of the translated PDF.

> Cloud / Docker deployment were part of the original MVP idea but are no longer the primary target.  
> This repository is now oriented to **local desktop usage** on Windows.

---

## 1. Features

- Upload a single PDF and translate a page range (e.g. 1–50, 51–100).
- Choose source and target language (using a translation LLM behind an HTTP API).
- Simple extraction strategy selector (`auto`, `fast`, `hi_res`, `ocr_only` – currently used as metadata; the minimal implementation focuses on `auto`).
- Progress tracking in the same window:
  - status badge (`pending`, `partitioning`, `translating`, `rendering`, `completed`, `failed`, `cancelled`);
  - number of elements translated;
  - visual progress bar.
- **Automatic download** of the translated PDF when the job completes.
- **Cancel button** to stop an in-progress translation job.
- Architecture and plan for a **true Windows 11 desktop app** using `pywebview` and `PyInstaller`.

---

## 2. Project structure (high level)

Key directories and files:

- `app/`
  - `main.py` – FastAPI application factory (`create_app`).
  - `routes/ui.py` – HTML pages (upload/status UI).
  - `routes/jobs.py` – JSON API for jobs (create, query, download, cancel).
  - `services/jobs.py` – job lifecycle, PDF reading and writing, translation orchestration.
  - `services/translation_llm_client.py` – HTTP client wrapper to the translation LLM.
  - `services/models.py` – Pydantic models for in-memory job tracking.
- `templates/`
  - `upload.html` – main UI page (upload + current job card + progress).
  - `job_status.html` – legacy status page (still available, but not used in the main flow).
- `storage/`
  - `original/` – original uploaded PDFs.
  - `output/` – translated PDFs.
- `requirements.txt` – Python runtime dependencies.
- `desktop-app-plan.md` – detailed plan for wrapping the FastAPI app into a Windows 11 desktop executable using `pywebview` and `PyInstaller`.
- `pdf-translator-mvp-architecture.md` / `PRD — Serviço Python “PDF Book Translator” (LLM).md` – original architecture and product notes (kept as reference).

> Docker-related files have been removed. Deployment is now oriented toward local development and later packaging into a Windows `.exe`.

---

## 3. Requirements

Recommended environment:

- Windows 11 (desktop-focused UX).
- Python 3.11 (or compatible 3.10+).
- Local LLM runtime:
  - Typically **Ollama** running Translategemma, or
  - Another HTTP-based translation API compatible with `TranslationClient`.

Python dependencies (installed from `requirements.txt`):

- fastapi
- uvicorn[standard]
- httpx
- pypdf
- fpdf2
- Jinja2
- python-multipart
- pywebview

For building a desktop executable later:

- `pyinstaller` (dev-only, not listed in `requirements.txt`).

---

## 4. Configuration (LLM backend)

The translation client is configured via environment variables:

- `TRANSLATION_LLM_BASE_URL`  
  Default: `http://localhost:11534`  
  Example (Ollama running Translategemma locally): `http://localhost:11434` or `http://localhost:11534`.

- `TRANSLATION_LLM_MODEL_NAME`  
  Default: `translategemma`

Optional environment variables for future backends (remote API, etc.) are described in `desktop-app-plan.md`. Currently the code assumes a simple HTTP JSON interface compatible with Translategemma.

---

## 5. Running in development (browser)

In dev mode, you typically run the FastAPI app directly and open it in the browser.

```bash
git clone https://github.com/<your-username>/translater.git
cd translater

python -m venv .venv
.venv\Scripts\activate

pip install --upgrade pip
pip install -r requirements.txt
```

Make sure your LLM backend is running and reachable at `TRANSLATION_LLM_BASE_URL`. Then:

```bash
uvicorn app.main:create_app --host 127.0.0.1 --port 8000 --reload
```

Open:

```text
http://127.0.0.1:8000/
```

You should see the **PDF Translator** window-styled UI:

- Choose a PDF.
- Select source / target languages.
- Adjust page range if needed.
- Click **Send for translation**.

The **CURRENT JOB** card appears at the bottom, showing:

- current status and stage,
- translated elements,
- progress bar,
- a **Cancel translation** button.

When the job reaches `completed`, the browser automatically starts the download of the translated PDF.

---

## 6. Desktop mode (Windows 11, planned)

The repository already contains a detailed design for the desktop experience in  
[`desktop-app-plan.md`](desktop-app-plan.md).

Summary of the planned approach:

- Use `uvicorn` + `FastAPI` exactly as in development, but started in a background thread.
- Use `pywebview` to create a native window pointing to `http://127.0.0.1:8000`.
- Expose a small Python API (`DesktopApi`) to the front-end that can:
  - open a **native “Save As…” dialog** for the translated PDF;
  - handle other desktop-only actions (future settings, logs, etc.).
- Build `run_desktop.exe` using `PyInstaller`:
  - `pyinstaller --onefile --windowed run_desktop.py`

Once `run_desktop.py` is implemented, the typical user experience will be:

1. Double-click the desktop executable.
2. A window opens with the same dark UI you see in development.
3. Translating a PDF behaves the same, but:
   - when the job is completed, the app uses a Windows “Save As…” dialog so the user can choose where to store the translated PDF.

The design in `desktop-app-plan.md` is the authoritative reference for this mode.

---

## 7. Tests and quality

At the moment, the repository does not include formal automated tests.  
When adding tests, the recommended stack is:

- `pytest` for unit and integration tests.
- Separate tests for:
  - `JobService` (PDF handling, job status transitions, cancellation).
  - `TranslationClient` (mocked HTTP responses).
  - Template rendering / routes (FastAPI `TestClient`).

Contributions that add tests and linting (e.g. `ruff`, `mypy`) are welcome.

---

## 8. Contributing

Suggestions for contribution:

- Implement `run_desktop.py` as described in `desktop-app-plan.md`.
- Improve the translation strategies and support more languages.
- Add a settings page to switch between:
  - local LLM (Ollama),
  - remote translation APIs.
- Add unit/integration tests and CI workflows.

For pull requests:

- Keep the Python code readable and small, focused functions.
- Avoid introducing Docker-specific files unless the desktop story remains the primary focus.

---

## 9. License

The repository currently does not declare an explicit license.  
Before publishing publicly, you should choose and add a license file (for example MIT, Apache 2.0, etc.).

