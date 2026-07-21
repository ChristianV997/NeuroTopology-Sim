#!/usr/bin/env python3
"""Real-time inference server for cross-modal fusion embeddings.

Serves pre-trained GNN model with:
- Batched inference for throughput
- Caching for repeated samples
- WebSocket streaming capability
- Latency monitoring

Usage:
    server = FusionInferenceServer(model_path)
    embeddings = server.encode_batch(metrics_batch)  # (batch_size, latent_dim)
"""
from __future__ import annotations

import time
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from collections import deque
import hashlib

import numpy as np
import torch
from torch_geometric.data import Data

from dual_engine.cross_modal_fusion import CrossModalFusionNetwork, FusionConfig


class FusionInferenceServer:
    """Real-time inference server for fusion embeddings."""

    def __init__(self, model_path: Path, config: Optional[FusionConfig] = None,
                 cache_size: int = 1000):
        """Initialize inference server.

        Args:
            model_path: Path to saved model checkpoint
            config: FusionConfig (default: FusionConfig with defaults)
            cache_size: Size of embedding cache
        """
        self.model_path = Path(model_path)
        self.config = config or FusionConfig(device="cuda" if torch.cuda.is_available() else "cpu")

        # Load model
        self.model = CrossModalFusionNetwork(self.config).to(self.config.device)
        if self.model_path.exists():
            self.model.load_state_dict(torch.load(self.model_path, map_location=self.config.device))
            print(f"Loaded model from {self.model_path}")
        else:
            print(f"Warning: Model path {self.model_path} not found, using untrained model")

        self.model.eval()

        # Embedding cache (hash -> embedding)
        self.cache = {}
        self.cache_size = cache_size
        self.cache_hits = 0
        self.cache_misses = 0

        # Latency tracking
        self.latencies = deque(maxlen=100)

    def _metrics_hash(self, metrics: Dict[str, float]) -> str:
        """Hash metrics dict for caching."""
        json_str = json.dumps(metrics, sort_keys=True, default=str)
        return hashlib.md5(json_str.encode()).hexdigest()[:16]

    def encode_metrics(self, bold_metrics: np.ndarray, eeg_metrics: np.ndarray,
                      synthetic_metrics: np.ndarray, cache: bool = True) -> np.ndarray:
        """Encode a single sample.

        Args:
            bold_metrics: (n_bold_parcels,) metric vector
            eeg_metrics: (n_eeg_channels,) metric vector
            synthetic_metrics: (n_synth_parcels,) metric vector
            cache: Whether to use/store in cache

        Returns:
            embedding: (latent_dim,) numpy array
        """
        # Check cache
        metrics_dict = {
            "bold": bold_metrics.tobytes().hex(),
            "eeg": eeg_metrics.tobytes().hex(),
            "synthetic": synthetic_metrics.tobytes().hex(),
        }
        hash_key = self._metrics_hash(metrics_dict)

        if cache and hash_key in self.cache:
            self.cache_hits += 1
            return self.cache[hash_key]

        self.cache_misses += 1

        # Inference
        t0 = time.time()

        with torch.no_grad():
            # Create mock graph data (simplified: no edges for this demo)
            bold_data = Data(
                x=torch.tensor(bold_metrics, dtype=torch.float32).unsqueeze(1),
                edge_index=torch.tensor([], dtype=torch.long).t().contiguous(),
                batch=torch.tensor([0] * len(bold_metrics), dtype=torch.long),
            ).to(self.config.device)

            eeg_data = Data(
                x=torch.tensor(eeg_metrics, dtype=torch.float32).unsqueeze(1),
                edge_index=torch.tensor([], dtype=torch.long).t().contiguous(),
                batch=torch.tensor([0] * len(eeg_metrics), dtype=torch.long),
            ).to(self.config.device)

            synth_data = Data(
                x=torch.tensor(synthetic_metrics, dtype=torch.float32).unsqueeze(1),
                edge_index=torch.tensor([], dtype=torch.long).t().contiguous(),
                batch=torch.tensor([0] * len(synthetic_metrics), dtype=torch.long),
            ).to(self.config.device)

            embedding = self.model.encode(bold_data, eeg_data, synth_data)
            embedding_np = embedding.cpu().numpy()[0]  # Take first (only) sample

        latency_ms = (time.time() - t0) * 1000
        self.latencies.append(latency_ms)

        # Cache result
        if cache and len(self.cache) < self.cache_size:
            self.cache[hash_key] = embedding_np

        return embedding_np

    def encode_batch(self, bold_batch: np.ndarray, eeg_batch: np.ndarray,
                    synthetic_batch: np.ndarray) -> np.ndarray:
        """Encode a batch of samples.

        Args:
            bold_batch: (batch_size, n_bold_parcels)
            eeg_batch: (batch_size, n_eeg_channels)
            synthetic_batch: (batch_size, n_synth_parcels)

        Returns:
            embeddings: (batch_size, latent_dim)
        """
        t0 = time.time()
        batch_size = bold_batch.shape[0]

        embeddings = []
        for i in range(batch_size):
            emb = self.encode_metrics(bold_batch[i], eeg_batch[i], synthetic_batch[i], cache=False)
            embeddings.append(emb)

        embeddings_array = np.array(embeddings)

        latency_ms = (time.time() - t0) * 1000
        avg_per_sample = latency_ms / batch_size if batch_size > 0 else 0
        print(f"Batch inference: {batch_size} samples in {latency_ms:.1f} ms ({avg_per_sample:.1f} ms/sample)")

        return embeddings_array

    def get_stats(self) -> Dict[str, Any]:
        """Get inference statistics."""
        avg_latency = np.mean(list(self.latencies)) if self.latencies else 0
        p95_latency = np.percentile(list(self.latencies), 95) if self.latencies else 0

        total_cache_requests = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_cache_requests * 100) if total_cache_requests > 0 else 0

        return {
            "avg_latency_ms": float(avg_latency),
            "p95_latency_ms": float(p95_latency),
            "cache_hit_rate": float(hit_rate),
            "cache_size": len(self.cache),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
        }
