"""Modèles de l'inventaire pédagogique."""

from __future__ import annotations

from typing import Literal
import math

from pydantic import BaseModel, ConfigDict, Field, model_validator


ConceptType = Literal[
    "rule",
    "concept",
    "definition",
    "property",
    "theorem",
    "formula",
    "method",
    "protocol",
    "syntax",
    "command",
    "example",
    "remark",
]


class ConceptEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1)
    excerpt: str = Field(min_length=1, max_length=6000)


class SourceIllustration(BaseModel):
    """Zone du PDF original, jamais une image produite par le modèle."""
    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1)
    anchor_page: int = Field(ge=1)
    heading: str = Field(min_length=1, max_length=180)
    bbox: tuple[float, float, float, float]
    origin: Literal["unit", "page", "quote"] = "unit"

    @model_validator(mode="after")
    def validate_region(self):
        x0, y0, x1, y1 = self.bbox
        if not all(math.isfinite(v) for v in self.bbox) or not (0 <= x0 < x1 and 0 <= y0 < y1):
            raise ValueError("Zone d'illustration invalide")
        if self.page not in (self.anchor_page, self.anchor_page + 1):
            raise ValueError("Illustration trop éloignée de son titre source")
        return self


class LearningPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    point_id: str
    kind: Literal["explanation", "condition", "formula", "example", "alternatives", "steps", "advice", "illustration", "mention"]
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=6000)


class Concept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_id: str = Field(min_length=1, max_length=140)
    title: str = Field(min_length=1, max_length=180)
    source_anchor: str | None = Field(default=None, min_length=1, max_length=180)
    evidence_issue: str | None = Field(default=None, max_length=600)
    type: ConceptType
    primary_part_id: str = Field(min_length=1, max_length=120)
    related_part_ids: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(min_length=1)
    evidence: list[ConceptEvidence] = Field(min_length=1)
    illustrations: list[SourceIllustration] = Field(default_factory=list)
    learning_points: list[LearningPoint] = Field(default_factory=list)
    card_role: Literal["standalone", "support", "visual"] = "standalone"
    relevance: Literal["active", "mention_only"] = "active"
    relevance_reason: str | None = Field(default=None, max_length=600)
    relevance_file_hash: str | None = Field(default=None, min_length=32, max_length=128)
    relevance_proof_hash: str | None = Field(default=None, min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_sources(self):
        if sorted(set(self.source_pages)) != self.source_pages:
            raise ValueError("source_pages doit être trié et sans doublon")
        if any(item.page not in self.source_pages for item in self.evidence):
            raise ValueError("Chaque preuve doit appartenir à source_pages")
        if any(i.page not in self.source_pages or i.anchor_page not in self.source_pages for i in self.illustrations):
            raise ValueError("Chaque illustration et son titre doivent appartenir à source_pages")
        if self.primary_part_id in self.related_part_ids:
            raise ValueError("La partie principale ne doit pas être dupliquée dans related_part_ids")
        return self


class InventoryPartCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_id: str = Field(min_length=1, max_length=120)
    part_number: str = Field(pattern=r"^\d+$")
    status: Literal["complete", "error"]
    concepts_found: int = Field(ge=0)
    concepts_added_by_audit: int = Field(ge=0)
    audit_passes: int = Field(default=1, ge=1)
    message: str | None = Field(default=None, max_length=1200)


class ConceptInventory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=3, ge=1)
    course_id: str = Field(min_length=3, max_length=120)
    file_hash: str = Field(min_length=32, max_length=128)
    model: str = Field(min_length=1, max_length=120)
    parts: list[InventoryPartCoverage] = Field(default_factory=list)
    concepts: list[Concept] = Field(default_factory=list)
