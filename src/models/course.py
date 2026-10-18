"""Modèles de données d'un cours StudyPilot."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CourseMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    course_id: str = Field(min_length=3, max_length=120)
    title: str = Field(min_length=1, max_length=180)
    source_filename: str = Field(min_length=1, max_length=255)
    file_hash: str = Field(min_length=32, max_length=128)
    page_count: int = Field(ge=1)


class CourseRecord(CourseMetadata):
    """Métadonnées persistantes d'un cours."""

    original_filename: str | None = Field(default=None, max_length=255)
    uploaded_at: str | None = Field(default=None, max_length=80)
