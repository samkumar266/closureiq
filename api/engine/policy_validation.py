"""Validation helpers for the checked-in ClosureIQ policy document."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SUPPORTED_UNITS = frozenset({"mph", "in", "ft", "min"})
REQUIRED_THRESHOLD_IDS = tuple(f"T{number}" for number in range(1, 12))
PROPOSED_THRESHOLD_IDS = frozenset({"T12"})
SUPPORTED_ALERT_TIERS = frozenset({"warning", "watch", "advisory"})


class PolicyConfigurationError(ValueError):
    """Raised when policy configuration is missing or malformed."""


def policy_values(policy: Mapping[str, Any] | Any) -> Mapping[str, Any]:
    """Return a mapping from a raw mapping or a canonical Policy model."""

    if isinstance(policy, Mapping):
        return policy
    values = getattr(policy, "values", None)
    if isinstance(values, Mapping):
        return values
    raise PolicyConfigurationError("policy must be a mapping or expose mapping values")


def threshold_definitions(
    policy: Mapping[str, Any] | Any,
    *,
    include_proposed: bool = False,
) -> tuple[Mapping[str, Any], ...]:
    """Return validated active threshold definitions without activating T12."""

    values = policy_values(policy)
    thresholds = values.get("thresholds")
    if not isinstance(thresholds, list):
        raise PolicyConfigurationError("policy.thresholds must be a list")

    definitions: dict[str, Mapping[str, Any]] = {}
    for definition in thresholds:
        if not isinstance(definition, Mapping):
            raise PolicyConfigurationError("each threshold must be a mapping")
        threshold_id = definition.get("id")
        if not isinstance(threshold_id, str) or not threshold_id:
            raise PolicyConfigurationError("each threshold requires a non-empty id")
        if threshold_id in definitions:
            raise PolicyConfigurationError(f"duplicate threshold id: {threshold_id}")
        definitions[threshold_id] = definition

    missing = [item for item in REQUIRED_THRESHOLD_IDS if item not in definitions]
    if missing:
        raise PolicyConfigurationError(
            f"missing required threshold definitions: {', '.join(missing)}"
        )
    unexpected = set(definitions) - set(REQUIRED_THRESHOLD_IDS) - PROPOSED_THRESHOLD_IDS
    if unexpected:
        raise PolicyConfigurationError(
            f"thresholds are neither active nor proposed: {', '.join(sorted(unexpected))}"
        )

    active = tuple(
        definition
        for threshold_id, definition in definitions.items()
        if include_proposed or threshold_id not in PROPOSED_THRESHOLD_IDS
    )
    return active


def validate_policy(policy: Mapping[str, Any] | Any) -> None:
    """Validate threshold metadata and event mappings without applying policy rules."""

    values = policy_values(policy)
    thresholds = threshold_definitions(values)
    for definition in thresholds:
        _validate_threshold(definition)
    _validate_events(values.get("events"))

    proposed = {
        definition["id"]
        for definition in values["thresholds"]
        if definition["id"] in PROPOSED_THRESHOLD_IDS
    }
    if proposed != PROPOSED_THRESHOLD_IDS:
        missing = sorted(PROPOSED_THRESHOLD_IDS - proposed)
        raise PolicyConfigurationError(
            f"proposed threshold metadata is missing: {', '.join(missing)}"
        )
    for definition in values["thresholds"]:
        if definition["id"] in PROPOSED_THRESHOLD_IDS and definition.get("status") not in {
            "confirm",
            "proposed",
        }:
            raise PolicyConfigurationError(
                f"{definition['id']} must remain explicitly proposed or confirm"
            )


def _validate_threshold(definition: Mapping[str, Any]) -> None:
    threshold_id = definition["id"]
    for key in ("hazard", "input", "cutoff", "effect", "status"):
        if key not in definition:
            raise PolicyConfigurationError(f"{threshold_id} missing required field: {key}")
    status = definition["status"]
    if status not in {"verified", "confirm", "assumption"}:
        raise PolicyConfigurationError(f"{threshold_id} has unsupported status: {status}")
    cutoff = definition["cutoff"]
    if not isinstance(cutoff, (str, int, float, list, Mapping)) or isinstance(
        cutoff, bool
    ):
        raise PolicyConfigurationError(f"{threshold_id} has malformed cutoff")
    if isinstance(cutoff, (int, float)) and "unit" not in definition:
        raise PolicyConfigurationError(f"{threshold_id} numeric cutoff requires unit")
    if "unit" in definition and definition["unit"] not in SUPPORTED_UNITS:
        raise PolicyConfigurationError(
            f"{threshold_id} has unsupported unit: {definition['unit']}"
        )


def _validate_events(events: Any) -> None:
    if not isinstance(events, Mapping) or not events:
        raise PolicyConfigurationError("policy.events must be a non-empty mapping")
    for hazard, tiers in events.items():
        if not isinstance(hazard, str) or not isinstance(tiers, Mapping):
            raise PolicyConfigurationError("each event mapping must map a hazard to tiers")
        for tier, event_names in tiers.items():
            if tier not in SUPPORTED_ALERT_TIERS:
                raise PolicyConfigurationError(f"unsupported alert tier: {tier}")
            if not isinstance(event_names, list) or not all(
                isinstance(event_name, str) and event_name for event_name in event_names
            ):
                raise PolicyConfigurationError(
                    f"{hazard}.{tier} must be a non-empty list of event names"
                )
