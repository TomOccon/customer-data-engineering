"""dataguard: small, testable guards for the pipeline failure modes in the README."""

from .chunked_join import chunked_join
from .completeness import CompletenessResult, check_completeness, check_completeness_counts
from .governance import GovernanceConfig, audit_datasets, estimate_savings
from .joins import (
    JoinCardinalityReport,
    JoinFanoutError,
    assert_no_fanout,
    check_join_cardinality,
    composite_key,
    dedupe_latest,
)
from .reconcile import (
    ReconcileReport,
    ReconcileResult,
    ReconciliationError,
    reconcile_counts,
    reconcile_frames,
    reconcile_sums,
)

__all__ = [
    "chunked_join",
    "CompletenessResult",
    "check_completeness",
    "check_completeness_counts",
    "GovernanceConfig",
    "audit_datasets",
    "estimate_savings",
    "JoinCardinalityReport",
    "JoinFanoutError",
    "assert_no_fanout",
    "check_join_cardinality",
    "composite_key",
    "dedupe_latest",
    "ReconcileReport",
    "ReconcileResult",
    "ReconciliationError",
    "reconcile_counts",
    "reconcile_frames",
    "reconcile_sums",
]
