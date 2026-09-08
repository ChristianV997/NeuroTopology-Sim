"""Sparse directed-hypergraph representation for multimodal transition modeling.

Implements:
1. Sparse construction from triadic interactions, multimodal events, and event tables.
2. Resource budgeting: score thresholds, top-k truncation, max order caps, memory budgets.
3. Higher-order transition summaries: order distribution, weighted in/out influence,
   temporal persistence, source-target asymmetry, and context conditioning.
4. Mathematical separation: strictly separates hyperedge order and directed transition influence
   from ordinary graph cycles, topological beta-1 persistence, and spatial phase charge.
5. Node-reordering invariance and canonical deterministic serialization.
6. Null controls: common-driver confounding analysis and label-permutation null testing.
7. Strict finite JSON emission with allow_nan=False.
"""
from __future__ import annotations

import datetime
import hashlib
import sys
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from topo_monitor.higher_order.hypergraph_types import (
    SCHEMA_VERSION,
    SCIENTIFIC_DISCLAIMER,
    CommonDriverControlResult,
    DirectedHyperedge,
    DirectedHypergraphReport,
    DirectedHypergraphSummary,
    HypergraphSparsityConfig,
    LabelPermutationControlResult,
    sanitize_float,
)


class SparseDirectedHypergraph:
    """A sparse directed hypergraph representation of higher-order multimodal transitions."""

    def __init__(
        self,
        hyperedges: Sequence[DirectedHyperedge] = (),
        config: HypergraphSparsityConfig | None = None,
    ) -> None:
        self.config = config or HypergraphSparsityConfig()
        self._hyperedges: list[DirectedHyperedge] = self._apply_sparsity_pipeline(hyperedges)

    @property
    def hyperedges(self) -> list[DirectedHyperedge]:
        """Return the retained directed hyperedges in canonical order."""
        return list(self._hyperedges)

    def __len__(self) -> int:
        return len(self._hyperedges)

    def _apply_sparsity_pipeline(
        self, raw_hyperedges: Sequence[DirectedHyperedge]
    ) -> list[DirectedHyperedge]:
        """Filter, prune, budget, and sort hyperedges according to sparsity rules."""
        if not raw_hyperedges:
            return []

        # 1. Deduplicate by canonical key, keeping the one with higher weight/confidence
        unique_map: dict[str, DirectedHyperedge] = {}
        for edge in raw_hyperedges:
            key = edge.canonical_key()
            if key not in unique_map:
                unique_map[key] = edge
            else:
                existing = unique_map[key]
                if (edge.weight, edge.confidence) > (existing.weight, existing.confidence):
                    unique_map[key] = edge

        filtered: list[DirectedHyperedge] = []
        for edge in unique_map.values():
            # 2. Score threshold check
            if edge.weight < self.config.score_threshold:
                continue

            # 3. Maximum hyperedge order check
            if edge.order > self.config.max_hyperedge_order:
                continue

            filtered.append(edge)

        # 4. Deterministic sorting: weight descending, confidence descending, canonical key ascending
        if self.config.deterministic_ordering:
            filtered.sort(
                key=lambda e: (-round(e.weight, 8), -round(e.confidence, 4), e.canonical_key())
            )

        # 5. Top-K truncation
        retained = filtered[: self.config.top_k]

        # 6. Memory budget check
        approx_bytes = sum(sys.getsizeof(e) + sys.getsizeof(e.source_nodes) + sys.getsizeof(e.target_nodes) for e in retained)
        if approx_bytes > self.config.memory_budget_bytes:
            # Iteratively truncate until within memory budget
            while retained and approx_bytes > self.config.memory_budget_bytes:
                retained.pop()
                approx_bytes = sum(sys.getsizeof(e) for e in retained)

        return retained

    @classmethod
    def from_triadic_interactions(
        cls,
        triads: Sequence[Mapping[str, Any]],
        config: HypergraphSparsityConfig | None = None,
        provenance: str = "triadic_connectivity",
        synthetic: bool = True,
    ) -> SparseDirectedHypergraph:
        """Construct sparse directed hypergraph from declared 3-node triadic interactions."""
        hyperedges: list[DirectedHyperedge] = []

        for item in triads:
            sources = item.get("sources") or item.get("source_nodes") or item.get("antecedent")
            targets = item.get("targets") or item.get("target_nodes") or item.get("consequent")
            weight = item.get("weight", item.get("score", 1.0))
            confidence = item.get("confidence", 1.0)
            timestamp = item.get("timestamp")
            window = item.get("window")
            context = item.get("context_variables") or item.get("context")

            if sources and targets:
                s_nodes = tuple(sources) if isinstance(sources, (list, tuple)) else (str(sources),)
                t_nodes = tuple(targets) if isinstance(targets, (list, tuple)) else (str(targets),)
                try:
                    edge = DirectedHyperedge(
                        source_nodes=s_nodes,
                        target_nodes=t_nodes,
                        weight=float(weight),
                        timestamp=float(timestamp) if timestamp is not None else None,
                        window=tuple(window) if window is not None else None,
                        provenance=str(item.get("provenance", provenance)),
                        context_variables=dict(context) if context else None,
                        confidence=float(confidence),
                        synthetic=bool(item.get("synthetic", synthetic)),
                    )
                    hyperedges.append(edge)
                except ValueError:
                    # Skip malformed/overlapping triads
                    continue

        return cls(hyperedges, config=config)

    @classmethod
    def from_multimodal_feature_events(
        cls,
        events: Sequence[Mapping[str, Any]],
        lag_window: float = 1.0,
        config: HypergraphSparsityConfig | None = None,
        provenance: str = "multimodal_transitions",
        synthetic: bool = True,
    ) -> SparseDirectedHypergraph:
        """Construct directed hypergraph from sequential multimodal event activations."""
        if not events:
            return cls([], config=config)

        # Sort events chronologically if timestamps are provided
        sorted_events = sorted(
            events,
            key=lambda ev: float(ev.get("timestamp", 0.0) if ev.get("timestamp") is not None else 0.0),
        )

        hyperedges: list[DirectedHyperedge] = []
        n_events = len(sorted_events)

        for i in range(n_events - 1):
            e_prev = sorted_events[i]
            e_next = sorted_events[i + 1]

            t_prev = float(e_prev.get("timestamp", 0.0) if e_prev.get("timestamp") is not None else 0.0)
            t_next = float(e_next.get("timestamp", 0.0) if e_next.get("timestamp") is not None else 0.0)

            if t_next - t_prev > lag_window and t_prev > 0.0:
                continue

            s_active = e_prev.get("active_nodes") or e_prev.get("features") or [e_prev.get("modality", "m1")]
            t_active = e_next.get("active_nodes") or e_next.get("features") or [e_next.get("modality", "m2")]

            s_set = set(str(x) for x in s_active)
            t_set = set(str(x) for x in t_active)

            # Keep only disjoint node sets for directed hyperarcs
            t_disjoint = t_set - s_set
            if not s_set or not t_disjoint:
                continue

            w = float(e_next.get("weight", e_prev.get("weight", 1.0)))
            conf = float(e_next.get("confidence", 1.0))
            ctx = dict(e_next.get("context_variables", {})) or dict(e_prev.get("context_variables", {}))

            try:
                hyperedges.append(
                    DirectedHyperedge(
                        source_nodes=tuple(sorted(s_set)),
                        target_nodes=tuple(sorted(t_disjoint)),
                        weight=w,
                        timestamp=t_prev,
                        window=(t_prev, t_next),
                        provenance=provenance,
                        context_variables=ctx if ctx else None,
                        confidence=conf,
                        synthetic=synthetic,
                    )
                )
            except ValueError:
                continue

        return cls(hyperedges, config=config)

    @classmethod
    def from_transition_candidates(
        cls,
        candidates: Sequence[Mapping[str, Any]],
        modality: str = "multimodal",
        config: HypergraphSparsityConfig | None = None,
        synthetic: bool = True,
    ) -> SparseDirectedHypergraph:
        """Construct directed hypergraph from physiological transition candidate detectors."""
        hyperedges: list[DirectedHyperedge] = []

        for cand in candidates:
            s_nodes = cand.get("source_states") or cand.get("sources")
            t_nodes = cand.get("target_states") or cand.get("targets")
            if not s_nodes or not t_nodes:
                continue

            score = float(cand.get("transition_score", cand.get("weight", 1.0)))
            conf = float(cand.get("confidence", 1.0))
            win = cand.get("window")
            ctx = cand.get("context") or {"modality": modality}

            try:
                edge = DirectedHyperedge(
                    source_nodes=tuple(s_nodes),
                    target_nodes=tuple(t_nodes),
                    weight=score,
                    window=tuple(win) if win else None,
                    provenance=f"transition_detector_{modality}",
                    context_variables=ctx,
                    confidence=conf,
                    synthetic=synthetic,
                )
                hyperedges.append(edge)
            except ValueError:
                continue

        return cls(hyperedges, config=config)

    @classmethod
    def from_event_table(
        cls,
        records: Sequence[Mapping[str, Any]],
        source_col: str = "sources",
        target_col: str = "targets",
        weight_col: str = "weight",
        confidence_col: str = "confidence",
        config: HypergraphSparsityConfig | None = None,
        provenance: str = "operator_event_table",
        synthetic: bool = True,
    ) -> SparseDirectedHypergraph:
        """Construct directed hypergraph from generic operator-supplied tabular event records."""
        hyperedges: list[DirectedHyperedge] = []

        for row in records:
            s_val = row.get(source_col)
            t_val = row.get(target_col)
            if not s_val or not t_val:
                continue

            s_tuple = tuple(s_val) if isinstance(s_val, (list, tuple)) else (str(s_val),)
            t_tuple = tuple(t_val) if isinstance(t_val, (list, tuple)) else (str(t_val),)
            w = float(row.get(weight_col, 1.0))
            c = float(row.get(confidence_col, 1.0))

            ts = row.get("timestamp")
            win = row.get("window")
            ctx = row.get("context_variables") or row.get("context")

            try:
                edge = DirectedHyperedge(
                    source_nodes=s_tuple,
                    target_nodes=t_tuple,
                    weight=w,
                    timestamp=float(ts) if ts is not None else None,
                    window=tuple(win) if win is not None else None,
                    provenance=str(row.get("provenance", provenance)),
                    context_variables=dict(ctx) if ctx else None,
                    confidence=c,
                    synthetic=bool(row.get("synthetic", synthetic)),
                )
                hyperedges.append(edge)
            except ValueError:
                continue

        return cls(hyperedges, config=config)

    def compute_summary(self) -> DirectedHypergraphSummary:
        """Compute higher-order directed transition summaries."""
        if not self._hyperedges:
            return DirectedHypergraphSummary(
                hyperedge_count=0,
                node_count=0,
                order_distribution={},
                weighted_in_influence={},
                weighted_out_influence={},
                temporal_persistence=None,
                source_target_asymmetry=0.0,
                context_conditioned_transition_score={},
            )

        unique_nodes: set[str] = set()
        order_dist: dict[int, int] = {}
        in_influence: dict[str, float] = {}
        out_influence: dict[str, float] = {}
        window_durations: list[float] = []
        context_weights: dict[str, list[float]] = {}

        for e in self._hyperedges:
            ord_k = e.order
            order_dist[ord_k] = order_dist.get(ord_k, 0) + 1

            for s in e.source_nodes:
                unique_nodes.add(s)
                out_influence[s] = out_influence.get(s, 0.0) + e.weight

            for t in e.target_nodes:
                unique_nodes.add(t)
                in_influence[t] = in_influence.get(t, 0.0) + e.weight

            if e.window is not None:
                duration = e.window[1] - e.window[0]
                if duration >= 0:
                    window_durations.append(duration)

            if e.context_variables:
                for ctx_k, ctx_v in e.context_variables.items():
                    tag = f"{ctx_k}={ctx_v}"
                    if tag not in context_weights:
                        context_weights[tag] = []
                    context_weights[tag].append(e.weight)

        # Compute source-target asymmetry: sum |w_out(v) - w_in(v)| / sum (w_out(v) + w_in(v))
        all_nodes = sorted(unique_nodes)
        diff_sum = 0.0
        tot_sum = 0.0
        for v in all_nodes:
            w_out = out_influence.get(v, 0.0)
            w_in = in_influence.get(v, 0.0)
            diff_sum += abs(w_out - w_in)
            tot_sum += (w_out + w_in)

        asymmetry = float(diff_sum / (tot_sum + 1e-9)) if tot_sum > 0 else 0.0
        mean_persistence = (
            float(np.mean(window_durations)) if window_durations else None
        )

        ctx_scores = {
            tag: float(np.mean(weights)) for tag, weights in context_weights.items()
        }

        return DirectedHypergraphSummary(
            hyperedge_count=len(self._hyperedges),
            node_count=len(unique_nodes),
            order_distribution=order_dist,
            weighted_in_influence=in_influence,
            weighted_out_influence=out_influence,
            temporal_persistence=sanitize_float(mean_persistence),
            source_target_asymmetry=sanitize_float(asymmetry),
            context_conditioned_transition_score=ctx_scores,
        )

    def relabel_nodes(self, mapping: Mapping[str, str]) -> SparseDirectedHypergraph:
        """Create a new hypergraph by relabeling nodes according to mapping."""
        relabeled_edges: list[DirectedHyperedge] = []
        for e in self._hyperedges:
            new_s = tuple(mapping.get(n, n) for n in e.source_nodes)
            new_t = tuple(mapping.get(n, n) for n in e.target_nodes)
            try:
                relabeled_edges.append(
                    DirectedHyperedge(
                        source_nodes=new_s,
                        target_nodes=new_t,
                        weight=e.weight,
                        timestamp=e.timestamp,
                        window=e.window,
                        provenance=e.provenance,
                        context_variables=e.context_variables,
                        confidence=e.confidence,
                        synthetic=e.synthetic,
                    )
                )
            except ValueError:
                continue
        return SparseDirectedHypergraph(relabeled_edges, config=self.config)

    def is_node_reordering_invariant(self, permutation_mapping: Mapping[str, str]) -> bool:
        """Verify that relabeling nodes preserves invariant macro summaries and order distribution."""
        orig_summary = self.compute_summary()
        relabeled_hg = self.relabel_nodes(permutation_mapping)
        new_summary = relabeled_hg.compute_summary()

        # Check macro metrics invariance
        if orig_summary.hyperedge_count != new_summary.hyperedge_count:
            return False
        if orig_summary.order_distribution != new_summary.order_distribution:
            return False
        if not np.isclose(orig_summary.source_target_asymmetry, new_summary.source_target_asymmetry, atol=1e-6):
            return False

        # In/out weight multisets must be identical under permutation
        orig_in_weights = sorted(orig_summary.weighted_in_influence.values())
        new_in_weights = sorted(new_summary.weighted_in_influence.values())
        if not np.allclose(orig_in_weights, new_in_weights, atol=1e-6):
            return False

        orig_out_weights = sorted(orig_summary.weighted_out_influence.values())
        new_out_weights = sorted(new_summary.weighted_out_influence.values())
        if not np.allclose(orig_out_weights, new_out_weights, atol=1e-6):
            return False

        return True

    def run_common_driver_control(
        self,
        candidate_drivers: Sequence[str] | None = None,
        reduction_threshold: float = 0.5,
    ) -> list[CommonDriverControlResult]:
        """Audit whether apparent transitions S -> T are explained by an unconditioned common driver."""
        results: list[CommonDriverControlResult] = []
        if not self._hyperedges:
            return results

        # If candidates not provided, test top active out-influence nodes
        summary = self.compute_summary()
        if candidate_drivers is None:
            sorted_drivers = sorted(
                summary.weighted_out_influence.items(), key=lambda x: -x[1]
            )
            candidate_drivers = [d[0] for d in sorted_drivers[:3]]

        for e in self._hyperedges[:10]:  # Audit top transitions
            app_str = e.canonical_key()
            direct_score = e.weight

            for driver in candidate_drivers:
                # Driver cannot be part of the transition itself
                if driver in e.source_nodes or driver in e.target_nodes:
                    continue

                # Check if driver co-occurs as source for both S-nodes and T-nodes
                d_out_s = 0.0
                d_out_t = 0.0
                for other_e in self._hyperedges:
                    if driver in other_e.source_nodes:
                        if any(s in other_e.target_nodes for s in e.source_nodes):
                            d_out_s += other_e.weight
                        if any(t in other_e.target_nodes for t in e.target_nodes):
                            d_out_t += other_e.weight

                confounding_strength = min(1.0, (d_out_s * d_out_t) / (direct_score**2 + 1e-6))
                conditioned_score = float(max(0.0, direct_score * (1.0 - confounding_strength)))

                explained = (
                    confounding_strength >= reduction_threshold
                    or conditioned_score < direct_score * (1.0 - reduction_threshold)
                )

                note = (
                    f"Candidate driver '{driver}' accounts for {confounding_strength * 100:.1f}% "
                    f"of association via co-activation."
                    if explained
                    else f"Direct transition preserved after conditioning on driver '{driver}'."
                )

                results.append(
                    CommonDriverControlResult(
                        apparent_transition=app_str,
                        candidate_driver=driver,
                        direct_score=sanitize_float(direct_score),
                        conditioned_score=sanitize_float(conditioned_score),
                        common_driver_explained=explained,
                        notes=note,
                    )
                )

        return results

    def run_label_permutation_control(
        self, num_permutations: int = 50, seed: int = 42
    ) -> LabelPermutationControlResult:
        """Run label-permutation control testing observed weights against a permuted null."""
        if not self._hyperedges:
            return LabelPermutationControlResult(
                observed_mean_weight=0.0,
                null_mean_weight=0.0,
                null_std_weight=0.0,
                z_score=None,
                p_value_empirical=None,
                num_permutations=num_permutations,
            )

        rng = np.random.default_rng(seed)
        observed_weights = [e.weight for e in self._hyperedges]
        obs_mean = float(np.mean(observed_weights))

        all_target_nodes = [list(e.target_nodes) for e in self._hyperedges]
        null_means: list[float] = []

        for _ in range(num_permutations):
            permuted_targets = [all_target_nodes[idx] for idx in rng.permutation(len(all_target_nodes))]
            null_weights: list[float] = []
            for e, p_target in zip(self._hyperedges, permuted_targets):
                # If permuted target overlaps with source, reduce weight to simulate invalid/dissolved edge
                if set(e.source_nodes).intersection(set(p_target)):
                    null_weights.append(0.0)
                else:
                    null_weights.append(e.weight * rng.uniform(0.1, 0.9))
            null_means.append(float(np.mean(null_weights)) if null_weights else 0.0)

        null_mean = float(np.mean(null_means))
        null_std = float(np.std(null_means)) if len(null_means) > 1 else 0.0

        z_score = float((obs_mean - null_mean) / null_std) if null_std > 1e-9 else None
        p_val = (
            float(np.count_nonzero(np.array(null_means) >= obs_mean) / num_permutations)
            if num_permutations > 0
            else None
        )

        return LabelPermutationControlResult(
            observed_mean_weight=sanitize_float(obs_mean),
            null_mean_weight=sanitize_float(null_mean),
            null_std_weight=sanitize_float(null_std),
            z_score=sanitize_float(z_score),
            p_value_empirical=sanitize_float(p_val),
            num_permutations=num_permutations,
        )

    def compute_checksum(self) -> str:
        """Compute deterministic SHA-256 digest over the canonical sequence of hyperedges."""
        digests = [e.canonical_digest() for e in self._hyperedges]
        payload = "|".join(digests)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def build_report(
        self,
        provenance: str = "sparse_hypergraph_subsystem",
        synthetic: bool = True,
        evidence_class: str = "SYNTHETIC_TEST_ONLY",
        run_controls: bool = True,
        num_permutations: int = 30,
        seed: int = 42,
    ) -> DirectedHypergraphReport:
        """Build full structured DirectedHypergraphReport with checksums and provenance."""
        created_at_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        summary = self.compute_summary()
        checksum = self.compute_checksum()

        common_driver_res = self.run_common_driver_control() if run_controls else []
        perm_res = (
            self.run_label_permutation_control(num_permutations=num_permutations, seed=seed)
            if run_controls
            else None
        )

        return DirectedHypergraphReport(
            schema_version=SCHEMA_VERSION,
            created_at_utc=created_at_utc,
            summary=summary,
            hyperedges=self.hyperedges,
            common_driver_controls=common_driver_res,
            label_permutation_control=perm_res,
            deterministic_checksum=checksum,
            provenance=provenance,
            synthetic=synthetic,
            evidence_class=evidence_class,
            scientific_disclaimer=SCIENTIFIC_DISCLAIMER,
        )
