"""Canonical feature namespace for transition artifacts.

Every feature name must be namespaced as ``namespace.local_name``. The
namespace gates what kind of quantity a feature claims to be (a spectral
estimate, a topology invariant, a connectivity statistic, ...); the
canonical name list below is a *starter* registry, not an exhaustive
allowlist — new features under a known namespace are accepted so pipelines
can add metrics without touching this file, but the namespace itself must be
one of the ones declared here, and no feature name may imply a clinical,
diagnostic, or contemplative-attainment claim regardless of namespace.
"""
from __future__ import annotations

import re
import unicodedata

ALLOWED_NAMESPACES: frozenset[str] = frozenset(
    {
        "spectral",
        "topology",
        "connectivity",
        "dynamics",
        "complexity",
        "qc",
        "transition",
        "phenomenology",
        "phase_space",
        "experimental",
    }
)

# Restricted to at most exploratory_metric / computational_artifact claim
# scopes by transitions.governance.validate_governance — enforced there, not
# here, since this module has no notion of claim scope.
RESTRICTED_NAMESPACES: frozenset[str] = frozenset({"experimental"})

CANONICAL_FEATURES: frozenset[str] = frozenset(
    {
        "spectral.delta_power",
        "spectral.theta_power",
        "spectral.alpha_power",
        "spectral.beta_power",
        "spectral.gamma_power",
        "topology.q_net",
        "topology.q_abs",
        "topology.f_dress",
        "topology.defect_density",
        "topology.betti0",
        "topology.betti1",
        "topology.betti2",
        "topology.h1_persistence",
        "topology.persistence_landscape_area",
        "topology.bottleneck_distance",
        "connectivity.mean_plv",
        "connectivity.wpli",
        "connectivity.global_efficiency",
        "connectivity.modularity",
        "connectivity.degree",
        "dynamics.kuramoto_r",
        "dynamics.kuramoto_metastability",
        "dynamics.leida_state",
        "dynamics.leida_dwell_time",
        "dynamics.transition_probability",
        "complexity.pcist_proxy",
        "complexity.entropy",
        "complexity.lz_complexity",
        "qc.signal_quality",
        "qc.bad_channel_fraction",
        "qc.artifact_score",
        "transition.delta",
        "transition.velocity",
        "transition.acceleration",
        "transition.variance",
        "transition.dwell_time",
        "transition.hysteresis",
    }
)

# Forbidden regardless of namespace: a feature *name* must never itself
# encode a diagnostic, clinical, or contemplative-attainment claim. This is
# a name-level check, independent of (and in addition to)
# transitions.governance's claim_scope/evidence_level gate and the repo-wide
# sciencer_d.btc_icft.report_guardrails phrase firewall applied to free text.
FORBIDDEN_NAME_TOKENS: tuple[str, ...] = (
    "diagnos",  # diagnosis / diagnostic
    "treatment",
    "biomarker",
    "clinical",
    "psychiatric",
    "consciousness_detect",
    "consciousness_biomarker",
    "jhana",
    "cessation",
    "enlightenment",
    "spiritual_attainment",
    "meditation_stage_detect",
)

_NAME_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


class FeatureNameError(ValueError):
    """Raised when a feature name fails namespace or safety validation."""


def _normalize(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return folded.strip().lower().replace("-", "_").replace(" ", "_")


def validate_feature_name(name: str) -> None:
    """Raise FeatureNameError if `name` is not an acceptable feature name.

    Passes silently for any canonical name, and for any well-formed
    ``namespace.local_name`` under an allowed namespace that does not hit
    the forbidden-token list. Restriction of `experimental.*` to narrow
    claim scopes is enforced by transitions.governance, not here.
    """
    if not name or not isinstance(name, str):
        raise FeatureNameError("feature name must be a non-empty string")

    normalized = _normalize(name)

    for token in FORBIDDEN_NAME_TOKENS:
        if token in normalized:
            raise FeatureNameError(
                f"feature name '{name}' contains forbidden token '{token}' — "
                "feature names must not imply diagnosis, treatment, clinical "
                "biomarker status, consciousness detection, or contemplative "
                "attainment/cessation/enlightenment detection"
            )

    if name in CANONICAL_FEATURES:
        return

    if not _NAME_PATTERN.match(normalized):
        raise FeatureNameError(
            f"feature name '{name}' must be namespaced as 'namespace.local_name' "
            "(lowercase, alnum/underscore only)"
        )

    namespace = normalized.split(".", 1)[0]
    if namespace not in ALLOWED_NAMESPACES:
        raise FeatureNameError(
            f"feature name '{name}' uses unknown namespace '{namespace}'; "
            f"allowed namespaces: {sorted(ALLOWED_NAMESPACES)}"
        )


def validate_feature_names(names: list[str]) -> list[str]:
    """Return a list of error strings (empty = all valid). Never raises."""
    errors: list[str] = []
    if not names:
        errors.append("feature_names must not be empty")
        return errors
    for name in names:
        try:
            validate_feature_name(name)
        except FeatureNameError as exc:
            errors.append(str(exc))
    return errors


def validate_feature_names_or_raise(names: list[str]) -> None:
    errors = validate_feature_names(names)
    if errors:
        raise FeatureNameError("; ".join(errors))


def is_restricted_feature(name: str) -> bool:
    """True if `name`'s namespace caps the claim scope (currently: experimental.*)."""
    normalized = _normalize(name)
    if "." not in normalized:
        return False
    namespace = normalized.split(".", 1)[0]
    return namespace in RESTRICTED_NAMESPACES
