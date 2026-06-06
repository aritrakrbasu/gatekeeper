"""Knowledge assertion enumeration types."""

from __future__ import annotations

from enum import Enum


class AssertionType(str, Enum):
    REPOSITORY_PATTERN = "repository_pattern"
    BUSINESS_RULE = "business_rule"
    ARCHITECTURE_RULE = "architecture_rule"
    REVIEW_CORRECTION = "review_correction"


class AssertionStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class AuditAction(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
