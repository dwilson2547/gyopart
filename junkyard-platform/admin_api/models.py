from __future__ import annotations

import datetime

from pydantic import BaseModel, Field


class DiscrepancyGroup(BaseModel):
    source: str
    raw_make: str | None
    raw_model: str | None
    count: int
    vehicle_ids: list[int]
    best_make_match: str | None
    best_make_score: float | None
    best_model_match: str | None
    best_model_score: float | None
    candidate_car_id: int | None
    nhtsa_make: str | None = None
    nhtsa_model: str | None = None
    nhtsa_year: str | None = None


class DiscrepancyListResponse(BaseModel):
    groups: list[DiscrepancyGroup]
    total: int


class CreateRuleRequest(BaseModel):
    field: str = Field(..., pattern="^(make|model|trim)$")
    rule_type: str = Field(..., pattern="^(exact|prefix|regex)$")
    raw_value: str
    canonical_value: str
    scope: str = Field("global", pattern="^(global|source|location)$")
    source: str | None = None
    location_id: int | None = None
    make_context: str | None = None
    priority: int = Field(100, ge=1, le=1000)


class ManualOverrideRequest(BaseModel):
    car_id: int = Field(..., ge=1)


class RuleResponse(BaseModel):
    id: int
    scope: str
    source: str | None
    location_id: int | None
    field: str
    rule_type: str
    raw_value: str
    canonical_value: str
    make_context: str | None
    priority: int
    is_active: bool
    created_by: str
    created_at: datetime.datetime
    applied_count: int
    llm_confidence: float | None
    llm_rationale: str | None
    approved_at: datetime.datetime | None
    approved_by: str | None


class RuleListResponse(BaseModel):
    rules: list[RuleResponse]


class LlmSuggestion(BaseModel):
    rule_id: int
    field: str
    rule_type: str
    raw_value: str
    canonical_value: str
    make_context: str | None
    llm_confidence: float
    llm_rationale: str
    source: str
    affected_count: int


class LlmSuggestionListResponse(BaseModel):
    suggestions: list[LlmSuggestion]


class ReprocessResponse(BaseModel):
    triggered: bool
    message: str
