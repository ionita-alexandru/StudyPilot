"""Schémas du plan pédagogique d'un cours."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CoursePart(BaseModel):
    """Champs stables d'une partie ; les métadonnées du planner restent autorisées."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=120)
    number: str = Field(pattern=r"^\d+$")
    title: str = Field(min_length=1, max_length=180)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    source_pages: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_pages(self):
        if self.page_end < self.page_start:
            raise ValueError("page_end doit être supérieur ou égal à page_start")
        expected = list(range(self.page_start, self.page_end + 1))
        if self.source_pages != expected:
            raise ValueError("source_pages doit couvrir exactement la plage physique de la partie")
        return self


class CoursePlan(BaseModel):
    """Enveloppe canonique du plan actif."""

    model_config = ConfigDict(extra="allow")

    schema_version: int = Field(default=1, ge=1)
    course_id: str = Field(min_length=3, max_length=120)
    plan_version: int = Field(default=1, ge=1)
    filename: str = Field(min_length=1, max_length=255)
    file_hash: str = Field(min_length=32, max_length=128)
    page_count: int = Field(ge=1)
    parts: list[CoursePart] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_coverage(self):
        expected_page = 1
        for index, part in enumerate(self.parts, start=1):
            if part.number != str(index) or part.page_start != expected_page:
                raise ValueError("Les parties doivent être contiguës, ordonnées et numérotées")
            expected_page = part.page_end + 1
        if expected_page != self.page_count + 1:
            raise ValueError("Le plan doit couvrir toutes les pages du PDF exactement une fois")
        return self
