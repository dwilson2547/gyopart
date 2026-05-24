import re

from sqlalchemy.orm import Session

from junkyard_common.models import MappingRule, Vehicle


_SCOPE_PRIORITY = {"location": 0, "source": 1, "global": 2}


def _rule_matches(rule: MappingRule, field_value: str) -> bool:
    raw = rule.raw_value
    val = field_value.lower()
    match rule.rule_type:
        case "exact":
            return raw.lower() == val
        case "prefix":
            return val.startswith(raw.lower())
        case "regex":
            return bool(re.search(raw, field_value, re.IGNORECASE))
        case _:
            return False


def _rule_applies_to_vehicle(rule: MappingRule, vehicle: Vehicle, current_make: str) -> bool:
    if rule.scope == "location" and rule.location_id != getattr(vehicle, "location_id", None):
        return False
    if rule.scope == "source" and rule.source != getattr(vehicle, "source", None):
        return False
    if rule.make_context and current_make.lower() != rule.make_context.lower():
        return False
    return True


def apply_rules(
    vehicle: Vehicle,
    rules: list[MappingRule],
    session: Session,
    dry_run: bool = False,
) -> tuple[dict, list[MappingRule]]:
    """
    Apply active MappingRules to vehicle's make/model/trim.
    Returns (transformed_fields_dict, list_of_applied_rules).
    Scope priority: location > source > global. Within same scope, lower priority number wins.
    Increments applied_count on matched rules and commits.
    """
    transformed = {
        "make":  getattr(vehicle, "make",  "") or "",
        "model": getattr(vehicle, "model", "") or "",
        "trim":  getattr(vehicle, "trim",  "") or "",
    }
    applied: list[MappingRule] = []

    # Sort: ascending priority number within each scope level
    sorted_rules = sorted(rules, key=lambda r: (_SCOPE_PRIORITY[r.scope], r.priority))

    for field in ("make", "model", "trim"):
        field_rules = [r for r in sorted_rules if r.field == field and r.is_active]
        current_make = transformed["make"]
        for rule in field_rules:
            if not _rule_applies_to_vehicle(rule, vehicle, current_make):
                continue
            if _rule_matches(rule, transformed[field]):
                transformed[field] = rule.canonical_value
                rule.applied_count = (rule.applied_count or 0) + 1
                applied.append(rule)
                break  # first matching rule wins per field

    if applied and not dry_run:
        session.commit()

    return transformed, applied
