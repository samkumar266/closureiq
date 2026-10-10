"""Canonical Pydantic types for the ClosureIQ engine boundary."""

from __future__ import annotations

from datetime import datetime, time
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, model_serializer


class Posture(StrEnum):
    """The five contract postures, ordered from mildest to most restrictive."""

    NORMAL_OPERATIONS = "normal_operations"
    DELAYED_ARRIVAL = "delayed_arrival"
    EARLY_DISMISSAL = "early_dismissal"
    UNSCHEDULED_LEAVE_OR_TELEWORK = "unscheduled_leave_or_telework"
    CLOSURE = "closure"


class ConfidenceLevel(StrEnum):
    """Confidence values exposed by the recommendation contract."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class HazardClass(StrEnum):
    """Hazard classes configured by the policy."""

    THUNDERSTORM_WIND = "thunderstorm_wind"
    WINTER_STORM = "winter_storm"
    FLOOD = "flood"


class AlertTier(StrEnum):
    """NWS alert tiers exposed by the contract."""

    NONE = "none"
    ADVISORY = "advisory"
    WATCH = "watch"
    WARNING = "warning"


InputRole = Literal["drove", "context"]
DataMode = Literal["live", "replay"]


class InputEvidence(BaseModel):
    """A source observation with its replay provenance."""

    model_config = ConfigDict(extra="forbid")

    id: str
    role: InputRole
    source: str
    label: str
    value: float | int | dict[str, object] | None
    unit: str | None = None
    hazard: HazardClass | None = None
    onset: datetime | None = None
    ends: datetime | None = None
    fetched_at: datetime
    snapshot_id: str
    source_updated_at: datetime | None = None
    stale: bool = False
    ok: bool = True

    @model_serializer(mode="wrap")
    def serialize_preserving_input_shape(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        """Keep omitted optional fixture fields omitted during round trips."""

        serialized = handler(self)
        return {
            key: value
            for key, value in serialized.items()
            if key in self.__pydantic_fields_set__ or key in {"id", "role", "source", "label", "value", "fetched_at", "snapshot_id"}
        }


Evidence = InputEvidence


class FacilityPolicy(BaseModel):
    """Legacy flat facility timing profile used by the current engine."""

    model_config = ConfigDict(extra="forbid")

    facility_id: str
    timezone: str = "America/Chicago"
    open_time: time
    close_time: time
    arrival_start: time
    arrival_end: time
    departure_start: time
    departure_end: time
    commute_buffer_min: int = Field(ge=0)
    notification_lead_min: int = Field(ge=0)
    policy_version: str


class Facility(BaseModel):
    """Contract-shaped facility profile for the canonical interface."""

    model_config = ConfigDict(extra="forbid")

    facility_id: str
    name: str
    location: dict[str, float | str]
    hours: dict[str, time]
    arrival_window: dict[str, time]
    departure_window: dict[str, time]
    commute_buffer_min: int = Field(ge=0)
    notification_lead_min: int = Field(ge=0)
    earliest_departure: time
    assembly_point: str
    manager_id: str
    backup_manager_id: str
    on_call_id: str
    gauge: dict[str, str] | None
    policy_version: str

    def to_policy(self) -> FacilityPolicy:
        """Adapt the contract profile to the legacy engine timing profile."""

        timezone = self.location.get("timezone")
        if not isinstance(timezone, str):
            raise ValueError("facility.location.timezone must be a string")
        return FacilityPolicy(
            facility_id=self.facility_id,
            timezone=timezone,
            open_time=self.hours["open"],
            close_time=self.hours["close"],
            arrival_start=self.arrival_window["start"],
            arrival_end=self.arrival_window["end"],
            departure_start=self.departure_window["start"],
            departure_end=self.departure_window["end"],
            commute_buffer_min=self.commute_buffer_min,
            notification_lead_min=self.notification_lead_min,
            policy_version=self.policy_version,
        )


class Employee(BaseModel):
    """Contract-shaped roster employee."""

    model_config = ConfigDict(extra="forbid")

    employee_id: str
    name: str
    group: str
    assignment_type: str
    shift_start: time
    shift_end: time
    work_status_today: str
    essential: bool
    telework_eligible: bool
    commute_county: str | None
    channels: list[str]
    comm_needs: list[str]
    supervisor_id: str | None


class Policy(BaseModel):
    """Explicit policy input for the canonical interface."""

    model_config = ConfigDict(extra="allow")

    policy_version: str
    values: dict[str, Any] = Field(default_factory=dict)


class SourceHealth(BaseModel):
    """Freshness status supplied by ingestion or replay."""

    model_config = ConfigDict(extra="forbid")

    source: str
    status: Literal["fresh", "stale", "missing"]
    fetched_at: datetime | None
    last_good_snapshot_id: str | None
    last_good_age_minutes: float | None
    max_age_minutes: int
    reason: str | None


class EvaluationContext(BaseModel):
    """Prior state needed to apply deterministic hysteresis."""

    model_config = ConfigDict(extra="forbid")

    evaluation_id: str
    facility_id: str
    evaluated_at: datetime
    posture: Posture
    raw_posture: Posture
    held_by_hysteresis: bool = False


class Confidence(BaseModel):
    level: ConfidenceLevel
    reasons: list[str]


class MissingEvidence(BaseModel):
    source: str
    reason: str
    last_good_snapshot_id: str | None
    last_good_age_minutes: float | None
    max_age_minutes: int


class ThresholdResult(BaseModel):
    id: str
    input_id: str
    cutoff: str | int | float
    actual: str | int | float
    unit: str | None = None
    margin: float | None = None
    distance: float | None = None
    anchor: str | None = None
    anchor_url: str | None = None

    @model_serializer(mode="wrap")
    def serialize_preserving_input_shape(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        """Keep optional fields omitted when the fixture omitted them."""

        serialized = handler(self)
        return {
            key: value
            for key, value in serialized.items()
            if key in self.__pydantic_fields_set__ or key in {"id", "input_id", "cutoff", "actual"}
        }


class Flip(BaseModel):
    change: str
    resulting_posture: Posture
    note: str | None = None

    @model_serializer(mode="wrap")
    def serialize_preserving_input_shape(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        """Keep the optional note absent when it was absent in the fixture."""

        serialized = handler(self)
        return {
            key: value
            for key, value in serialized.items()
            if key in self.__pydantic_fields_set__ or key in {"change", "resulting_posture"}
        }


class Recommendation(BaseModel):
    """The complete recommendation object from docs/contract.md."""

    model_config = ConfigDict(extra="forbid")

    hypothetical: bool
    evaluation_id: str
    supersedes: str | None
    facility_id: str
    evaluated_at: datetime
    policy_version: str
    data_mode: DataMode
    posture: Posture
    raw_posture: Posture
    held_by_hysteresis: bool
    parameters: dict[str, object]
    safety_instruction: str | None
    decision_deadline: datetime | None
    confidence: Confidence
    inputs: list[InputEvidence]
    thresholds_crossed: list[ThresholdResult]
    thresholds_not_crossed: list[ThresholdResult]
    missing_evidence: list[MissingEvidence]
    flip_list: list[Flip]
    rationale: str


class WhatIfResult(Recommendation):
    """A hypothetical recommendation that is never a persisted evaluation."""

    based_on: str
    changed_fields: list[str]
