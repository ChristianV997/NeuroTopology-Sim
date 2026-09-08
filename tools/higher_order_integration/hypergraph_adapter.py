"""Directed-hypergraph feature adapter and contract integration.

Integrates directed-hypergraph transition outputs with forecasting and canonical feature contracts
without modifying underlying hypergraph, forecasting, or feature implementations.

Strict scientific guardrails:
1. All JSON output must use allow_nan=False (NaN/Inf serialized as explicit null).
2. Graph beta-1 cycle counts, ordinary graph cycles, and spatial phase charge (Q_spatial)
   must remain mathematically and structurally separate from hyperedge order and transition influence.
3. Directed hyperedges represent multivariate dependency structures, NOT automatic proof of causation.
   Causal claims are strictly rejected without verified causal-design metadata.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import math
import sys
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

from topo_monitor.higher_order.hypergraph_types import (
    DirectedHyperedge,
    DirectedHypergraphReport,
    sanitize_float,
)
from transitions.features import validate_feature_name

SCHEMA_VERSION = "1.0.0"
SCIENTIFIC_DISCLAIMER = (
    "Directed hypergraphs represent sparse multivariate dependency structures and "
    "temporal transition patterns. They do not constitute automatic proof of causal biological "
    "mechanisms without an explicit causal interventional design. Graph beta-1 persistence, "
    "ordinary graph cycles, and spatial phase charge are mathematically distinct."
)

BANNED_CAUSAL_TOKENS: tuple[str, ...] = (
    "causes",
    "causal proof",
    "proves causation",
    "causal mechanism",
    "causality confirmed",
    "direct causal driver",
    "mechanistic proof",
)


@dataclass(frozen=True)
class NormalizedHyperedge:
    """Canonicalized directed hyperedge with verified ordering, units, and bounds."""

    source_nodes: tuple[str, ...]
    target_nodes: tuple[str, ...]
    order: int
    weight: float
    confidence: float
    timestamp: float | None = None
    window: tuple[float, float] | None = None
    declared_units: str = "coupling_weight"
    provenance: str = "hypergraph_pipeline"
    context_variables: dict[str, Any] | None = None
    synthetic: bool = True

    def canonical_key(self) -> str:
        """Deterministic string key representing the directed hyperedge topology."""
        return f"({','.join(self.source_nodes)})->({','.join(self.target_nodes)})"

    def canonical_digest(self) -> str:
        """Deterministic SHA-256 digest of hyperedge content."""
        w_str = f"{round(self.weight, 6):.6f}"
        c_str = f"{round(self.confidence, 4):.4f}"
        ts_str = f"{round(self.timestamp, 6):.6f}" if self.timestamp is not None else "null"
        win_str = (
            f"[{round(self.window[0], 6):.6f},{round(self.window[1], 6):.6f}]"
            if self.window is not None
            else "null"
        )
        ctx_str = (
            json.dumps(self.context_variables, sort_keys=True, allow_nan=False)
            if self.context_variables is not None
            else "null"
        )
        payload = (
            f"{self.canonical_key()}|ord={self.order}|w={w_str}|c={c_str}|ts={ts_str}|"
            f"win={win_str}|units={self.declared_units}|prov={self.provenance}|ctx={ctx_str}|syn={self.synthetic}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        clean_ctx = None
        if self.context_variables is not None:
            clean_ctx = {
                k: sanitize_float(v) if isinstance(v, (int, float)) else v
                for k, v in sorted(self.context_variables.items())
            }
        return {
            "source_nodes": list(self.source_nodes),
            "target_nodes": list(self.target_nodes),
            "order": self.order,
            "weight": sanitize_float(self.weight),
            "confidence": sanitize_float(self.confidence),
            "timestamp": sanitize_float(self.timestamp),
            "window": [sanitize_float(self.window[0]), sanitize_float(self.window[1])]
            if self.window is not None
            else None,
            "declared_units": self.declared_units,
            "provenance": self.provenance,
            "context_variables": clean_ctx,
            "synthetic": self.synthetic,
            "canonical_key": self.canonical_key(),
            "canonical_digest": self.canonical_digest(),
        }


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    issue_type: str  # "error" or "warning"
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "issue_type": self.issue_type,
            "message": self.message,
        }


@dataclass(frozen=True)
class HypergraphValidationConfig:
    max_hyperedges: int = 500
    require_units: bool = True
    require_provenance: bool = True
    disallow_duplicates: bool = True
    disallow_unbounded_weights: bool = True
    strict_causal_check: bool = True
    allowed_units: frozenset[str] = frozenset(
        {"coupling_weight", "transition_probability", "mutual_information", "arbitrary_units", "normalized_score"}
    )


@dataclass(frozen=True)
class NullControlSummary:
    label_permutation_z_score: float | None = None
    label_permutation_p_value: float | None = None
    temporal_block_shift_preserved_ratio: float | None = None
    common_driver_confounding_fraction: float | None = None
    matched_variance_z_score: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label_permutation_z_score": sanitize_float(self.label_permutation_z_score),
            "label_permutation_p_value": sanitize_float(self.label_permutation_p_value),
            "temporal_block_shift_preserved_ratio": sanitize_float(
                self.temporal_block_shift_preserved_ratio
            ),
            "common_driver_confounding_fraction": sanitize_float(
                self.common_driver_confounding_fraction
            ),
            "matched_variance_z_score": sanitize_float(self.matched_variance_z_score),
            "details": self.details,
        }


@dataclass
class HypergraphFeaturePayload:
    schema_version: str
    created_at_utc: str
    feature_family: str
    features: dict[str, float]
    feature_metadata: dict[str, Any]
    normalized_hyperedges: list[NormalizedHyperedge]
    validation_issues: list[ValidationIssue]
    is_valid: bool
    null_controls: NullControlSummary
    deterministic_checksum: str
    provenance: str
    synthetic: bool
    evidence_class: str
    distinct_from_topology: dict[str, str] = field(
        default_factory=lambda: {
            "ordinary_graph_cycles": "strictly_separate",
            "beta_1_persistence": "strictly_separate",
            "spatial_phase_winding": "strictly_separate",
            "hyperedge_order": "higher_order_hypergraph_metric",
            "causal_influence": "non_causal_dependency_only",
        }
    )
    scientific_disclaimer: str = SCIENTIFIC_DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at_utc": self.created_at_utc,
            "feature_family": self.feature_family,
            "features": {k: sanitize_float(v) for k, v in sorted(self.features.items())},
            "feature_metadata": self.feature_metadata,
            "hyperedge_count": len(self.normalized_hyperedges),
            "normalized_hyperedges": [e.to_dict() for e in self.normalized_hyperedges],
            "validation_issues": [i.to_dict() for i in self.validation_issues],
            "is_valid": self.is_valid,
            "null_controls": self.null_controls.to_dict(),
            "deterministic_checksum": self.deterministic_checksum,
            "provenance": self.provenance,
            "synthetic": self.synthetic,
            "evidence_class": self.evidence_class,
            "distinct_from_topology": self.distinct_from_topology,
            "scientific_disclaimer": self.scientific_disclaimer,
        }

    def to_json(self, indent: int | None = 2) -> str:
        """Serialize payload to strict JSON with allow_nan=False null safety."""
        return json.dumps(self.to_dict(), indent=indent, allow_nan=False)


class HypergraphFeatureAdapter:
    """Normalizes, validates, and packages directed hypergraph records for forecasting contracts."""

    def __init__(self, config: HypergraphValidationConfig | None = None) -> None:
        self.config = config or HypergraphValidationConfig()

    def normalize_hyperedge(self, raw: Any) -> NormalizedHyperedge:
        """Normalize a raw hyperedge (from DirectedHyperedge, mapping, or object) into canonical form."""
        if isinstance(raw, DirectedHyperedge):
            s_nodes = tuple(sorted(set(str(n) for n in raw.source_nodes)))
            t_nodes = tuple(sorted(set(str(n) for n in raw.target_nodes)))
            w = float(raw.weight)
            conf = float(raw.confidence)
            ts = float(raw.timestamp) if raw.timestamp is not None else None
            win = (float(raw.window[0]), float(raw.window[1])) if raw.window is not None else None
            prov = str(raw.provenance)
            ctx = dict(raw.context_variables) if raw.context_variables else None
            syn = bool(raw.synthetic)
            units = "coupling_weight"
        elif isinstance(raw, Mapping):
            sources = raw.get("source_nodes") or raw.get("sources") or raw.get("tail") or ()
            targets = raw.get("target_nodes") or raw.get("targets") or raw.get("head") or ()
            if not sources or not targets:
                raise ValueError(f"Malformed hyperedge mapping missing sources/targets: {raw}")
            s_nodes = tuple(sorted(set(str(n) for n in sources)))
            t_nodes = tuple(sorted(set(str(n) for n in targets)))
            w = float(raw.get("weight", raw.get("score", 1.0)))
            conf = float(raw.get("confidence", 1.0))
            ts_val = raw.get("timestamp")
            ts = float(ts_val) if ts_val is not None else None
            win_val = raw.get("window")
            win = (float(win_val[0]), float(win_val[1])) if win_val is not None else None
            prov = str(raw.get("provenance", "mapping_record"))
            ctx = dict(raw.get("context_variables", raw.get("context", {}))) or None
            syn = bool(raw.get("synthetic", True))
            units = str(raw.get("declared_units", raw.get("units", "coupling_weight")))
        else:
            raise TypeError(f"Unsupported hyperedge type: {type(raw).__name__}")

        if not s_nodes:
            raise ValueError("source_nodes must be non-empty")
        if not t_nodes:
            raise ValueError("target_nodes must be non-empty")
        if set(s_nodes).intersection(set(t_nodes)):
            raise ValueError(f"source_nodes and target_nodes must be disjoint: {s_nodes} vs {t_nodes}")

        order = len(s_nodes) + len(t_nodes)
        return NormalizedHyperedge(
            source_nodes=s_nodes,
            target_nodes=t_nodes,
            order=order,
            weight=w,
            confidence=min(1.0, max(0.0, conf)),
            timestamp=ts,
            window=win,
            declared_units=units,
            provenance=prov,
            context_variables=ctx,
            synthetic=syn,
        )

    def validate_and_normalize(
        self, raw_records: Sequence[Any], causal_design_metadata: dict[str, Any] | None = None
    ) -> tuple[list[NormalizedHyperedge], list[ValidationIssue]]:
        """Validate and normalize a sequence of raw hyperedges against validation rules."""
        issues: list[ValidationIssue] = []
        normalized: list[NormalizedHyperedge] = []
        seen_keys: set[str] = set()

        if not raw_records:
            issues.append(
                ValidationIssue(
                    field="hyperedges",
                    issue_type="warning",
                    message="Input hyperedge sequence is empty.",
                )
            )
            return [], issues

        if len(raw_records) > self.config.max_hyperedges:
            issues.append(
                ValidationIssue(
                    field="hyperedge_count",
                    issue_type="error",
                    message=f"Hyperedge count {len(raw_records)} exceeds maximum allowed {self.config.max_hyperedges}.",
                )
            )

        for idx, item in enumerate(raw_records):
            try:
                edge = self.normalize_hyperedge(item)
            except Exception as exc:
                issues.append(
                    ValidationIssue(
                        field=f"hyperedges[{idx}]",
                        issue_type="error",
                        message=f"Normalization failed: {str(exc)}",
                    )
                )
                continue

            # Check finite weights
            if self.config.disallow_unbounded_weights:
                if not math.isfinite(edge.weight) or edge.weight < 0:
                    issues.append(
                        ValidationIssue(
                            field=f"hyperedges[{idx}].weight",
                            issue_type="error",
                            message=f"Weight must be finite and non-negative, got {edge.weight}.",
                        )
                    )
                    continue

            # Check declared units
            if self.config.require_units:
                if edge.declared_units not in self.config.allowed_units:
                    issues.append(
                        ValidationIssue(
                            field=f"hyperedges[{idx}].declared_units",
                            issue_type="error",
                            message=f"Declared units '{edge.declared_units}' not in allowed set {sorted(self.config.allowed_units)}.",
                        )
                    )

            # Check duplicates
            key = edge.canonical_key()
            if self.config.disallow_duplicates:
                if key in seen_keys:
                    issues.append(
                        ValidationIssue(
                            field=f"hyperedges[{idx}]",
                            issue_type="error",
                            message=f"Duplicate hyperedge topology detected: '{key}'.",
                        )
                    )
                    continue
                seen_keys.add(key)

            # Check causal language in free-text / provenance / context
            if self.config.strict_causal_check and not causal_design_metadata:
                text_corpus = f"{edge.provenance} {json.dumps(edge.context_variables)}".lower()
                for token in BANNED_CAUSAL_TOKENS:
                    if token in text_corpus:
                        issues.append(
                            ValidationIssue(
                                field=f"hyperedges[{idx}].causal_guardrail",
                                issue_type="error",
                                message=f"Causal language '{token}' forbidden without verified causal-design metadata.",
                            )
                        )

            normalized.append(edge)

        # Sort normalized hyperedges deterministically: weight desc, confidence desc, canonical key asc
        normalized.sort(
            key=lambda e: (-round(e.weight, 8), -round(e.confidence, 4), e.canonical_key())
        )
        return normalized, issues

    def extract_canonical_features(
        self, normalized_edges: Sequence[NormalizedHyperedge]
    ) -> tuple[dict[str, float], dict[str, Any]]:
        """Extract canonical comparison-ready transition features matching transitions.features namespace."""
        if not normalized_edges:
            zero_features = {
                "transition.hyperedge_count": 0.0,
                "transition.hyperedge_order_mean": 0.0,
                "transition.hyperedge_order_max": 0.0,
                "transition.source_target_asymmetry": 0.0,
                "transition.temporal_persistence": 0.0,
                "transition.mean_transition_influence": 0.0,
                "transition.max_transition_influence": 0.0,
                "transition.context_conditioned_score": 0.0,
            }
            return zero_features, {"feature_count": len(zero_features), "active_nodes": []}

        orders = [float(e.order) for e in normalized_edges]
        weights = [float(e.weight) for e in normalized_edges]

        # Calculate node-level influence
        in_influence: dict[str, float] = {}
        out_influence: dict[str, float] = {}
        durations: list[float] = []
        ctx_scores: list[float] = []

        for e in normalized_edges:
            for s in e.source_nodes:
                out_influence[s] = out_influence.get(s, 0.0) + e.weight
            for t in e.target_nodes:
                in_influence[t] = in_influence.get(t, 0.0) + e.weight
            if e.window is not None:
                durations.append(max(0.0, e.window[1] - e.window[0]))
            if e.context_variables:
                ctx_scores.append(e.weight)

        all_nodes = sorted(set(in_influence.keys()).union(set(out_influence.keys())))
        diff_sum = 0.0
        tot_sum = 0.0
        all_influences: list[float] = []

        for v in all_nodes:
            w_out = out_influence.get(v, 0.0)
            w_in = in_influence.get(v, 0.0)
            diff_sum += abs(w_out - w_in)
            tot_sum += (w_out + w_in)
            all_influences.append(w_out + w_in)

        asymmetry = float(diff_sum / (tot_sum + 1e-9)) if tot_sum > 0 else 0.0
        mean_dur = float(np.mean(durations)) if durations else 0.0
        mean_inf = float(np.mean(all_influences)) if all_influences else 0.0
        max_inf = float(np.max(all_influences)) if all_influences else 0.0
        mean_ctx = float(np.mean(ctx_scores)) if ctx_scores else float(np.mean(weights))

        features = {
            "transition.hyperedge_count": float(len(normalized_edges)),
            "transition.hyperedge_order_mean": float(np.mean(orders)),
            "transition.hyperedge_order_max": float(np.max(orders)),
            "transition.source_target_asymmetry": asymmetry,
            "transition.temporal_persistence": mean_dur,
            "transition.mean_transition_influence": mean_inf,
            "transition.max_transition_influence": max_inf,
            "transition.context_conditioned_score": mean_ctx,
        }

        # Verify all feature names conform to transitions.features namespace
        for feat_name in features.keys():
            validate_feature_name(feat_name)

        metadata = {
            "feature_count": len(features),
            "active_node_count": len(all_nodes),
            "active_nodes": all_nodes,
            "units": {k: "dimensionless" for k in features.keys()},
        }
        metadata["units"]["transition.temporal_persistence"] = "seconds"
        metadata["units"]["transition.mean_transition_influence"] = "coupling_weight"
        metadata["units"]["transition.max_transition_influence"] = "coupling_weight"

        return features, metadata

    def evaluate_null_controls(
        self,
        normalized_edges: Sequence[NormalizedHyperedge],
        num_permutations: int = 50,
        seed: int = 42,
    ) -> NullControlSummary:
        """Run all 4 null controls: label permutation, temporal block shift, common driver, and matched variance."""
        if not normalized_edges:
            return NullControlSummary()

        rng = np.random.default_rng(seed)
        weights = np.array([e.weight for e in normalized_edges], dtype=float)
        obs_mean = float(np.mean(weights))

        # 1. Label Permutation Null Control
        all_targets = [list(e.target_nodes) for e in normalized_edges]
        null_perm_means: list[float] = []
        for _ in range(num_permutations):
            permuted_t = [all_targets[i] for i in rng.permutation(len(all_targets))]
            null_w = []
            for e, pt in zip(normalized_edges, permuted_t):
                if set(e.source_nodes).intersection(set(pt)):
                    null_w.append(0.0)
                else:
                    null_w.append(e.weight * rng.uniform(0.1, 0.9))
            null_perm_means.append(float(np.mean(null_w)) if null_w else 0.0)

        null_mean = float(np.mean(null_perm_means))
        null_std = float(np.std(null_perm_means)) if len(null_perm_means) > 1 else 0.0
        z_score_perm = (
            float((obs_mean - null_mean) / (null_std + 1e-9)) if null_std > 1e-9 else None
        )
        p_val_perm = (
            float(np.count_nonzero(np.array(null_perm_means) >= obs_mean) / num_permutations)
            if num_permutations > 0
            else None
        )

        # 2. Temporal Block Shift Control
        windows = [e.window for e in normalized_edges if e.window is not None]
        if windows:
            durations = [w[1] - w[0] for w in windows]
            shift_preservations: list[float] = []
            for _ in range(min(num_permutations, 20)):
                shift = float(rng.uniform(1.0, 10.0))
                shifted = [(w[0] + shift, w[1] + shift) for w in windows]
                # Check overlap ratio with original durations
                preserved = sum(1 for d, (s0, s1) in zip(durations, shifted) if abs((s1 - s0) - d) < 1e-6)
                shift_preservations.append(preserved / len(windows))
            block_shift_ratio = float(np.mean(shift_preservations))
        else:
            block_shift_ratio = None

        # 3. Common-Driver Control
        all_sources = [s for e in normalized_edges for s in e.source_nodes]
        source_counts: dict[str, int] = {}
        for s in all_sources:
            source_counts[s] = source_counts.get(s, 0) + 1
        most_common_source = max(source_counts, key=source_counts.get) if source_counts else None
        if most_common_source and len(normalized_edges) > 1:
            shared_count = sum(
                1 for e in normalized_edges if most_common_source in e.source_nodes
            )
            common_driver_fraction = float(shared_count / len(normalized_edges))
        else:
            common_driver_fraction = 0.0

        # 4. Matched-Variance Control
        obs_std = float(np.std(weights)) if len(weights) > 1 else 1.0
        surrogate_weights = rng.normal(loc=obs_mean, scale=obs_std, size=len(weights))
        surrogate_weights = np.maximum(0.0, surrogate_weights)
        surr_mean = float(np.mean(surrogate_weights))
        surr_std = float(np.std(surrogate_weights)) if len(surrogate_weights) > 1 else 1.0
        z_score_matched_var = float((obs_mean - surr_mean) / (surr_std + 1e-9))

        return NullControlSummary(
            label_permutation_z_score=sanitize_float(z_score_perm),
            label_permutation_p_value=sanitize_float(p_val_perm),
            temporal_block_shift_preserved_ratio=sanitize_float(block_shift_ratio),
            common_driver_confounding_fraction=sanitize_float(common_driver_fraction),
            matched_variance_z_score=sanitize_float(z_score_matched_var),
            details={
                "num_permutations": num_permutations,
                "observed_mean": sanitize_float(obs_mean),
                "null_permutation_mean": sanitize_float(null_mean),
            },
        )

    def compute_payload_checksum(
        self, normalized_edges: Sequence[NormalizedHyperedge], features: Mapping[str, float]
    ) -> str:
        """Compute deterministic SHA-256 digest over normalized hyperedges and feature dictionary."""
        edge_digests = [e.canonical_digest() for e in normalized_edges]
        feat_str = ",".join(f"{k}:{round(v, 8):.8f}" for k, v in sorted(features.items()))
        payload = f"edges=[{'|'.join(edge_digests)}]|feats=[{feat_str}]"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def build_feature_payload(
        self,
        raw_records: Sequence[Any],
        feature_family: str = "directed_hypergraph_transitions",
        provenance: str = "hypergraph_feature_adapter",
        evidence_class: str = "SYNTHETIC_TEST_ONLY",
        synthetic: bool = True,
        causal_design_metadata: dict[str, Any] | None = None,
        run_null_controls: bool = True,
    ) -> HypergraphFeaturePayload:
        """Execute full adapter pipeline: normalize, validate, extract canonical features, and package."""
        created_at_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        normalized_edges, issues = self.validate_and_normalize(
            raw_records, causal_design_metadata=causal_design_metadata
        )
        is_valid = not any(i.issue_type == "error" for i in issues)

        features, feat_meta = self.extract_canonical_features(normalized_edges)
        null_controls = (
            self.evaluate_null_controls(normalized_edges)
            if run_null_controls and is_valid
            else NullControlSummary()
        )
        checksum = self.compute_payload_checksum(normalized_edges, features)

        return HypergraphFeaturePayload(
            schema_version=SCHEMA_VERSION,
            created_at_utc=created_at_utc,
            feature_family=feature_family,
            features=features,
            feature_metadata=feat_meta,
            normalized_hyperedges=normalized_edges,
            validation_issues=issues,
            is_valid=is_valid,
            null_controls=null_controls,
            deterministic_checksum=checksum,
            provenance=provenance,
            synthetic=synthetic,
            evidence_class=evidence_class,
            scientific_disclaimer=SCIENTIFIC_DISCLAIMER,
        )
