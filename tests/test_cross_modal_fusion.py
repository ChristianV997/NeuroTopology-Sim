#!/usr/bin/env python3
"""Tests for cross-modal fusion engine."""
import pytest
import numpy as np
import torch
from pathlib import Path
from torch_geometric.data import Data

from dual_engine.cross_modal_fusion import (
    FusionConfig,
    CrossModalFusionNetwork,
    CrossModalFusionEngine,
)
from dual_engine.fusion_validation import FusionValidator, GateResult, PermutationResult


class TestFusionConfig:
    """Test configuration parsing."""

    def test_default_config(self):
        config = FusionConfig()
        assert config.latent_dim == 64
        assert config.num_heads == 4
        assert config.learning_rate == 0.001

    def test_config_cuda_device(self):
        config = FusionConfig(device="cpu")
        assert config.device == "cpu"


class TestCrossModalFusionNetwork:
    """Test the fusion network architecture."""

    @pytest.fixture
    def config(self):
        return FusionConfig(device="cpu")

    @pytest.fixture
    def network(self, config):
        return CrossModalFusionNetwork(config, num_nodes=360)

    def test_network_initialization(self, network):
        assert network is not None
        assert network.config.latent_dim == 64

    def test_encode_shapes(self, network):
        """Test that encoding produces correct shapes."""
        batch_size = 4

        # Create dummy graph data
        bold_data = Data(
            x=torch.randn(batch_size * 360, 1),
            edge_index=torch.tensor([[0, 1], [1, 0]], dtype=torch.long).t().contiguous(),
            batch=torch.repeat_interleave(torch.arange(batch_size), 360),
        )

        eeg_data = Data(
            x=torch.randn(batch_size * 20, 1),
            edge_index=torch.tensor([[0, 1], [1, 0]], dtype=torch.long).t().contiguous(),
            batch=torch.repeat_interleave(torch.arange(batch_size), 20),
        )

        synth_data = Data(
            x=torch.randn(batch_size * 360, 1),
            edge_index=torch.tensor([[0, 1], [1, 0]], dtype=torch.long).t().contiguous(),
            batch=torch.repeat_interleave(torch.arange(batch_size), 360),
        )

        # Encode
        latent = network.encode(bold_data, eeg_data, synth_data)
        assert latent.shape == (batch_size, 64)

    def test_decode_shapes(self, network):
        """Test reconstruction shapes."""
        latent = torch.randn(4, 64)
        bold_recon, eeg_recon, synth_recon = network.decode(latent)

        assert bold_recon.shape == (4, 360)
        assert eeg_recon.shape == (4, 360)
        assert synth_recon.shape == (4, 360)

    def test_forward_pass(self, network):
        """Test full forward pass."""
        batch_size = 4

        bold_data = Data(
            x=torch.randn(batch_size * 360, 1),
            edge_index=torch.tensor([[0, 1], [1, 0]], dtype=torch.long).t().contiguous(),
            batch=torch.repeat_interleave(torch.arange(batch_size), 360),
        )

        eeg_data = Data(
            x=torch.randn(batch_size * 20, 1),
            edge_index=torch.tensor([[0, 1], [1, 0]], dtype=torch.long).t().contiguous(),
            batch=torch.repeat_interleave(torch.arange(batch_size), 20),
        )

        synth_data = Data(
            x=torch.randn(batch_size * 360, 1),
            edge_index=torch.tensor([[0, 1], [1, 0]], dtype=torch.long).t().contiguous(),
            batch=torch.repeat_interleave(torch.arange(batch_size), 360),
        )

        latent, bold_recon, eeg_recon, synth_recon = network(bold_data, eeg_data, synth_data)

        assert latent.shape == (batch_size, 64)
        assert bold_recon.shape == (batch_size, 360)
        assert eeg_recon.shape == (batch_size, 360)
        assert synth_recon.shape == (batch_size, 360)


class TestFusionEngine:
    """Test the fusion training engine."""

    @pytest.fixture
    def engine(self, tmp_path):
        config = FusionConfig(device="cpu", num_epochs=2, batch_size=4)
        return CrossModalFusionEngine(config, output_dir=tmp_path)

    def test_engine_initialization(self, engine):
        assert engine.model is not None
        assert engine.optimizer is not None

    def test_contrastive_loss(self, engine):
        """Test contrastive loss computation."""
        embeddings = torch.randn(8, 64)
        labels = torch.tensor([0, 0, 1, 1, 2, 2, 3, 3])

        loss = engine.contrastive_loss(embeddings, labels)
        assert loss.item() > 0
        assert not torch.isnan(loss)

    def test_reconstruction_loss(self, engine):
        """Test reconstruction loss."""
        batch_size = 4
        latent_dim = 64
        num_nodes = 360

        recon = torch.randn(batch_size, num_nodes)
        target = torch.randn(batch_size, num_nodes)

        loss = engine.reconstruction_loss(recon, recon, recon, target, target, target)
        assert loss.item() > 0

    def test_encode_batch(self, engine):
        """Test batch encoding."""
        batch_size = 4

        bold_data = Data(
            x=torch.randn(batch_size * 360, 1),
            edge_index=torch.tensor([[0, 1], [1, 0]], dtype=torch.long).t().contiguous(),
            batch=torch.repeat_interleave(torch.arange(batch_size), 360),
        )

        eeg_data = Data(
            x=torch.randn(batch_size * 20, 1),
            edge_index=torch.tensor([[0, 1], [1, 0]], dtype=torch.long).t().contiguous(),
            batch=torch.repeat_interleave(torch.arange(batch_size), 20),
        )

        synth_data = Data(
            x=torch.randn(batch_size * 360, 1),
            edge_index=torch.tensor([[0, 1], [1, 0]], dtype=torch.long).t().contiguous(),
            batch=torch.repeat_interleave(torch.arange(batch_size), 360),
        )

        embeddings = engine.encode_batch(bold_data, eeg_data, synth_data)
        assert embeddings.shape == (batch_size, 64)


class TestFusionValidator:
    """Test validation framework."""

    @pytest.fixture
    def engine(self, tmp_path):
        config = FusionConfig(device="cpu")
        return CrossModalFusionEngine(config, output_dir=tmp_path)

    @pytest.fixture
    def validator(self, engine):
        return FusionValidator(engine)

    def test_phase_randomization(self, validator):
        """Test phase randomization preserves magnitude spectrum."""
        embeddings = np.random.randn(100, 64)

        # Phase randomize
        null_emb = validator.phase_randomize_embeddings(embeddings, seed=42)

        # Check shapes match
        assert null_emb.shape == embeddings.shape

        # Check magnitude spectrum preserved (FFT magnitude should be similar)
        for dim in range(embeddings.shape[1]):
            mag_real = np.abs(np.fft.fft(embeddings[:, dim]))
            mag_null = np.abs(np.fft.fft(null_emb[:, dim]))
            assert np.allclose(mag_real, mag_null, atol=1e-10)

    def test_embedding_distance_metric(self, validator):
        """Test distance metric computation."""
        embeddings = np.random.randn(50, 64)
        distance = validator.embedding_distance_metric(embeddings)

        assert isinstance(distance, float)
        assert distance > 0

    def test_surrogate_gate(self, validator):
        """Test surrogate gate produces valid results."""
        embeddings = np.random.randn(50, 64)
        result = validator.surrogate_gate(embeddings, n_surrogates=50)

        assert isinstance(result, GateResult)
        assert result.real_mean > 0
        assert result.z_score is not None
        assert 0 <= result.p_value <= 1

    def test_permutation_test(self, validator):
        """Test permutation test."""
        embeddings = np.random.randn(50, 64)
        condition_labels = np.array([0, 1] * 25)

        result = validator.permutation_test(embeddings, condition_labels, n_perms=100)

        assert isinstance(result, PermutationResult)
        assert result.real_effect >= 0
        assert 0 <= result.p_value <= 1

    def test_cross_dataset_generalization(self, validator):
        """Test cross-dataset generalization."""
        # Create synthetic train and test embeddings
        train_embeddings = np.random.randn(30, 64)
        train_labels = np.array([0, 1] * 15)

        test_embeddings = np.random.randn(20, 64)
        test_labels = np.array([0, 1] * 10)

        results = validator.cross_dataset_generalization(
            train_embeddings, train_labels, test_embeddings, test_labels
        )

        assert "accuracy" in results
        assert "auc" in results
        assert "f1" in results
        assert 0 <= results["accuracy"] <= 1
        assert 0 <= results["auc"] <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
