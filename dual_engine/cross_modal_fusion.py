#!/usr/bin/env python3
"""Cross-modal fusion engine: unified latent representation of BOLD + EEG + synthetic topology.

Architecture:
- Graph Neural Network backbone (GCNConv layers) over parcellated/electrode connectivity
- Cross-modal attention module for BOLD ↔ EEG ↔ synthetic embedding fusion
- Contrastive + reconstruction loss for unsupervised/weakly-supervised training
- Validation via surrogate gates + permutation resistance

Intended usage:
    fusion = CrossModalFusionEngine(config)
    embeddings = fusion.encode(bold_metrics, eeg_metrics, synthetic_metrics)
    # embeddings shape: (n_samples, latent_dim)
"""
from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor
from torch_geometric.nn import GCNConv, Sequential as GeoSequential, global_mean_pool
from torch_geometric.data import Data, DataLoader
from torch.optim import Adam
from torch.utils.tensorboard import SummaryWriter


@dataclass
class FusionConfig:
    """Cross-modal fusion hyperparameters."""
    hidden_dim: int = 64
    latent_dim: int = 64
    num_heads: int = 4
    num_gcn_layers: int = 2
    dropout: float = 0.1
    learning_rate: float = 1e-3
    weight_decay: float = 1e-5
    contrastive_temp: float = 0.1
    recon_weight: float = 0.5
    contrastive_weight: float = 1.0
    batch_size: int = 32
    num_epochs: int = 50
    device: str = "cuda" if torch.cuda.is_available() else "cpu"


class CrossModalAttention(nn.Module):
    """Multi-head cross-modal attention for BOLD, EEG, synthetic embeddings."""

    def __init__(self, embed_dim: int, num_heads: int):
        super().__init__()
        self.embed_dim = embed_dim
        self.num_heads = num_heads
        self.head_dim = embed_dim // num_heads

        assert embed_dim % num_heads == 0, "embed_dim must be divisible by num_heads"

        self.query = nn.Linear(embed_dim, embed_dim)
        self.key = nn.Linear(embed_dim, embed_dim)
        self.value = nn.Linear(embed_dim, embed_dim)
        self.fc_out = nn.Linear(embed_dim, embed_dim)

    def forward(self, bold: Tensor, eeg: Tensor, synthetic: Tensor) -> Tensor:
        """Fuse three modality embeddings via cross-attention.

        Args:
            bold: (batch, embed_dim)
            eeg: (batch, embed_dim)
            synthetic: (batch, embed_dim)

        Returns:
            fused: (batch, embed_dim) unified representation
        """
        batch_size = bold.shape[0]

        # Treat BOLD as query, EEG and synthetic as key-value
        Q = self.query(bold).reshape(batch_size, self.num_heads, self.head_dim)
        K = self.key(torch.cat([eeg, synthetic], dim=0)).reshape(-1, self.num_heads, self.head_dim)
        V = self.value(torch.cat([eeg, synthetic], dim=0)).reshape(-1, self.num_heads, self.head_dim)

        # Attention scores
        scores = torch.einsum('bhd,khd->bhk', Q, K) / np.sqrt(self.head_dim)
        attn_weights = F.softmax(scores, dim=-1)

        # Attend to values (aggregate EEG + synthetic for each BOLD sample)
        attended = torch.einsum('bhk,khd->bhd', attn_weights, V)
        attended = attended.reshape(batch_size, self.embed_dim)

        # Residual connection + output projection
        fused = self.fc_out(attended)
        fused = fused + bold  # Residual

        return fused


class CrossModalFusionNetwork(nn.Module):
    """GNN + attention network for cross-modal topology fusion."""

    def __init__(self, config: FusionConfig, num_nodes: int = 360, node_feature_dim: int = 1):
        super().__init__()
        self.config = config
        self.num_nodes = num_nodes

        # Per-modality GCN encoders. plain torch.nn.Sequential only chains a
        # single positional tensor between modules, but GCNConv needs both
        # (x, edge_index) at every layer -- torch_geometric.nn.Sequential's
        # 'args -> out' signature strings thread edge_index through each
        # GCNConv call while passing only x through the plain nn layers.
        #
        # The first GCNConv's in_channels must be `node_feature_dim` (the
        # per-node input feature width, e.g. 1 scalar per node), NOT
        # `num_nodes` (the graph's node count) -- those are unrelated
        # quantities. `num_nodes` is still correct for the decoders below,
        # which reconstruct a dense (batch, num_nodes) vector per graph.
        def _make_gcn() -> GeoSequential:
            return GeoSequential('x, edge_index', [
                (GCNConv(node_feature_dim, config.hidden_dim), 'x, edge_index -> x'),
                nn.ReLU(inplace=True),
                nn.Dropout(config.dropout),
                (GCNConv(config.hidden_dim, config.latent_dim), 'x, edge_index -> x'),
            ])

        self.bold_gcn = _make_gcn()
        self.eeg_gcn = _make_gcn()
        self.synthetic_gcn = _make_gcn()

        # Cross-modal attention
        self.attention = CrossModalAttention(config.latent_dim, config.num_heads)

        # Reconstruction heads (modality-specific decoders)
        self.bold_decoder = nn.Sequential(
            nn.Linear(config.latent_dim, config.hidden_dim),
            nn.ReLU(),
            nn.Linear(config.hidden_dim, num_nodes),
        )

        self.eeg_decoder = nn.Sequential(
            nn.Linear(config.latent_dim, config.hidden_dim),
            nn.ReLU(),
            nn.Linear(config.hidden_dim, num_nodes),
        )

        self.synthetic_decoder = nn.Sequential(
            nn.Linear(config.latent_dim, config.hidden_dim),
            nn.ReLU(),
            nn.Linear(config.hidden_dim, num_nodes),
        )

    def encode(self, bold_data: Data, eeg_data: Data, synthetic_data: Data) -> Tensor:
        """Encode three modality graphs to unified latent representation.

        Args:
            bold_data: torch_geometric.data.Data with x (node features) and edge_index
            eeg_data: torch_geometric.data.Data
            synthetic_data: torch_geometric.data.Data

        Returns:
            latent: (batch, latent_dim) unified embedding
        """
        # Encode per-modality
        bold_emb = self.bold_gcn(bold_data.x, bold_data.edge_index)
        bold_emb = global_mean_pool(bold_emb, bold_data.batch)

        eeg_emb = self.eeg_gcn(eeg_data.x, eeg_data.edge_index)
        eeg_emb = global_mean_pool(eeg_emb, eeg_data.batch)

        synth_emb = self.synthetic_gcn(synthetic_data.x, synthetic_data.edge_index)
        synth_emb = global_mean_pool(synth_emb, synthetic_data.batch)

        # Fuse via attention
        latent = self.attention(bold_emb, eeg_emb, synth_emb)

        return latent

    def decode(self, latent: Tensor) -> Tuple[Tensor, Tensor, Tensor]:
        """Reconstruct per-modality metrics from latent representation.

        Args:
            latent: (batch, latent_dim)

        Returns:
            bold_recon, eeg_recon, synthetic_recon: (batch, num_nodes) reconstructions
        """
        bold_recon = self.bold_decoder(latent)
        eeg_recon = self.eeg_decoder(latent)
        synth_recon = self.synthetic_decoder(latent)

        return bold_recon, eeg_recon, synth_recon

    def forward(self, bold_data: Data, eeg_data: Data, synthetic_data: Data) -> Tuple[Tensor, Tensor, Tensor, Tensor]:
        """Forward pass: encode + decode + return latent and reconstructions.

        Returns:
            latent, bold_recon, eeg_recon, synthetic_recon
        """
        latent = self.encode(bold_data, eeg_data, synthetic_data)
        bold_recon, eeg_recon, synth_recon = self.decode(latent)

        return latent, bold_recon, eeg_recon, synth_recon


class CrossModalFusionEngine:
    """Trainer and inference wrapper for cross-modal fusion."""

    def __init__(self, config: FusionConfig | None = None, output_dir: Path | None = None):
        self.config = config or FusionConfig()
        self.output_dir = Path(output_dir or "artifacts/fusion")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.model = CrossModalFusionNetwork(self.config).to(self.config.device)
        self.optimizer = Adam(self.model.parameters(), lr=self.config.learning_rate,
                             weight_decay=self.config.weight_decay)
        self.writer = SummaryWriter(str(self.output_dir / "logs"))

        # Save config
        (self.output_dir / "config.json").write_text(
            json.dumps({k: str(v) if not isinstance(v, (int, float, bool)) else v
                       for k, v in asdict(self.config).items()}, indent=2)
        )

    def contrastive_loss(self, embeddings: Tensor, labels: Tensor) -> Tensor:
        """Contrastive loss: same-subject embeddings should be close, different subjects far.

        Args:
            embeddings: (batch, latent_dim)
            labels: (batch,) subject IDs

        Returns:
            loss: scalar
        """
        # Normalize
        embeddings = F.normalize(embeddings, p=2, dim=1)

        # Compute pairwise similarities
        sim = torch.mm(embeddings, embeddings.t()) / self.config.contrastive_temp

        # Create target: 1 if same subject, 0 otherwise
        target = (labels.unsqueeze(0) == labels.unsqueeze(1)).float()
        target.fill_diagonal_(0)  # Exclude self

        # InfoNCE loss
        pos_mask = target
        neg_mask = 1 - target - torch.eye(embeddings.shape[0], device=embeddings.device)

        pos = torch.exp(sim) * pos_mask
        neg = torch.exp(sim) * neg_mask

        loss = -torch.log(pos.sum(dim=1) / (pos.sum(dim=1) + neg.sum(dim=1)) + 1e-8).mean()

        return loss

    def reconstruction_loss(self, bold_recon: Tensor, eeg_recon: Tensor, synth_recon: Tensor,
                          bold_target: Tensor, eeg_target: Tensor, synth_target: Tensor) -> Tensor:
        """Reconstruction loss across modalities."""
        loss = (F.mse_loss(bold_recon, bold_target) +
                F.mse_loss(eeg_recon, eeg_target) +
                F.mse_loss(synth_recon, synth_target)) / 3.0
        return loss

    def train_epoch(self, train_loader: DataLoader, subject_labels: np.ndarray) -> float:
        """Train one epoch."""
        self.model.train()
        total_loss = 0.0

        for i, (bold_batch, eeg_batch, synth_batch) in enumerate(train_loader):
            bold_batch = bold_batch.to(self.config.device)
            eeg_batch = eeg_batch.to(self.config.device)
            synth_batch = synth_batch.to(self.config.device)

            # Forward pass
            latent, bold_recon, eeg_recon, synth_recon = self.model(bold_batch, eeg_batch, synth_batch)

            # Losses
            batch_subject_labels = torch.tensor(subject_labels[i*self.config.batch_size:(i+1)*self.config.batch_size],
                                               device=self.config.device)

            cont_loss = self.contrastive_loss(latent, batch_subject_labels)
            recon_loss = self.reconstruction_loss(bold_recon, eeg_recon, synth_recon,
                                                  bold_batch.x, eeg_batch.x, synth_batch.x)

            loss = (self.config.contrastive_weight * cont_loss +
                   self.config.recon_weight * recon_loss)

            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()

            total_loss += loss.item()

        avg_loss = total_loss / (i + 1)
        return avg_loss

    def train(self, train_loader: DataLoader, subject_labels: np.ndarray, num_epochs: int | None = None):
        """Train cross-modal fusion model."""
        num_epochs = num_epochs or self.config.num_epochs

        for epoch in range(num_epochs):
            loss = self.train_epoch(train_loader, subject_labels)
            self.writer.add_scalar("train/loss", loss, epoch)

            if (epoch + 1) % 10 == 0:
                print(f"Epoch {epoch+1}/{num_epochs}: loss={loss:.4f}")

        # Save checkpoint
        torch.save(self.model.state_dict(), self.output_dir / "fusion_model.pt")
        print(f"Model saved to {self.output_dir / 'fusion_model.pt'}")

    def encode_batch(self, bold_data: Data, eeg_data: Data, synthetic_data: Data) -> np.ndarray:
        """Encode a batch to latent embeddings (inference mode)."""
        self.model.eval()
        with torch.no_grad():
            bold_data = bold_data.to(self.config.device)
            eeg_data = eeg_data.to(self.config.device)
            synthetic_data = synthetic_data.to(self.config.device)

            latent = self.model.encode(bold_data, eeg_data, synthetic_data)

        return latent.cpu().numpy()

    def load_checkpoint(self, checkpoint_path: Path):
        """Load trained model from checkpoint."""
        self.model.load_state_dict(torch.load(checkpoint_path, map_location=self.config.device))
        print(f"Loaded checkpoint from {checkpoint_path}")
