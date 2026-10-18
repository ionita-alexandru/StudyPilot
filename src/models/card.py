"""Modèles des fiches pédagogiques adaptatives."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models.concept import ConceptType, SourceIllustration


class CardSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=6000)


class StudyCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card_id: str = Field(min_length=1, max_length=140)
    concept_id: str = Field(min_length=1, max_length=140)

    title: str = Field(min_length=1, max_length=180)
    concept_type: ConceptType

    primary_part_id: str = Field(min_length=1, max_length=120)
    related_part_ids: list[str] = Field(default_factory=list)

    sections: list[CardSection] = Field(min_length=1)
    source_pages: list[int] = Field(min_length=1)
    illustrations: list[SourceIllustration] = Field(default_factory=list)
    covered_concept_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_card(self):
        if any(i.page not in self.source_pages or i.anchor_page not in self.source_pages for i in self.illustrations):
            raise ValueError("Illustration hors des pages sources de la fiche")
        if sorted(set(self.source_pages)) != self.source_pages:
            raise ValueError(
                "source_pages doit être trié et sans doublon"
            )

        if self.primary_part_id in self.related_part_ids:
            raise ValueError(
                "La partie principale ne doit pas être répétée "
                "dans related_part_ids"
            )

        keys = [
            section.key
            for section in self.sections
        ]

        if len(keys) != len(set(keys)):
            raise ValueError(
                "Les sections d'une fiche doivent avoir "
                "des clés uniques"
            )

        return self


class CardPartCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_id: str = Field(min_length=1, max_length=120)
    part_number: str = Field(pattern=r"^\d+$")

    status: Literal["complete", "partial", "error"]
    cards_generated: int = Field(ge=0)

    message: str | None = Field(
        default=None,
        max_length=1200,
    )


class BlockedCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    concept_id: str
    title: str
    primary_part_id: str
    source_pages: list[int]
    status: Literal["source_insufficient", "generation_error", "mention_only", "review_pending", "extraction_ambiguous", "card_incomplete"] = "source_insufficient"
    reason: str


class CardCollection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(
        default=6,
        ge=1,
    )

    course_id: str = Field(
        min_length=3,
        max_length=120,
    )
    file_hash: str = Field(
        min_length=32,
        max_length=128,
    )

    inventory_hash: str = Field(
        min_length=32,
        max_length=128,
    )
    model: str = Field(
        min_length=1,
        max_length=120,
    )

    parts: list[CardPartCoverage] = Field(
        default_factory=list
    )
    cards: list[StudyCard] = Field(
        default_factory=list
    )
    blocked: list[BlockedCard] = Field(default_factory=list)
    failures: list[BlockedCard] = Field(default_factory=list)
    ignored: list[BlockedCard] = Field(default_factory=list)
    concept_hashes: dict[str, str] = Field(default_factory=dict)
    unreviewed_cards: list[StudyCard] = Field(default_factory=list)
    archived_cards: list[StudyCard] = Field(default_factory=list)
    quality_version: int = 0
    quality_hash: str = ""
    review_issues: list[dict] = Field(default_factory=list)
    relations: list[dict] = Field(default_factory=list)
