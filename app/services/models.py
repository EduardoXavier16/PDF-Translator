from typing import Optional

from pydantic import BaseModel


class JobModel(BaseModel):
    id: str
    status: str
    total_elements: int
    translated_elements: int
    current_stage: str
    source_lang: str
    target_lang: str
    error: Optional[str]
