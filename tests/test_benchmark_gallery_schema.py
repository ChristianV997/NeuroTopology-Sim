"""Tests for `benchmark_packs.gallery.BenchmarkGalleryV1` and
`benchmark_packs.gallery_renderer.BenchmarkGalleryIndexV1`: dict
roundtrip, id determinism, and structural validation rules."""
from __future__ import annotations

from benchmark_packs.gallery import BenchmarkGalleryV1, compute_gallery_id
from benchmark_packs.gallery_renderer import BenchmarkGalleryIndexV1, compute_gallery_index_id


def _valid_gallery(**overrides):
    kwargs = dict(
        gallery_name="Test Gallery", benchmark_pack_paths=["a/BenchmarkPack.json", "b/BenchmarkPack.json"],
        limitations=["test gallery"], provenance="test",
    )
    kwargs.update(overrides)
    return BenchmarkGalleryV1.make(**kwargs)


def _valid_gallery_index(**overrides):
    kwargs = dict(gallery_id="gallery1", title="Test Gallery", limitations=["test index"])
    kwargs.update(overrides)
    return BenchmarkGalleryIndexV1.make(**kwargs)


# -- BenchmarkGalleryV1 --


def test_gallery_to_dict_from_dict_roundtrip():
    gallery = _valid_gallery(verified_pack_ids=["p1"], failed_pack_ids=["p2"])
    restored = BenchmarkGalleryV1.from_dict(gallery.to_dict())
    assert restored == gallery


def test_gallery_to_json_from_json_roundtrip():
    gallery = _valid_gallery()
    restored = BenchmarkGalleryV1.from_json(gallery.to_json())
    assert restored == gallery


def test_gallery_id_stable_for_identical_inputs():
    a = _valid_gallery()
    b = _valid_gallery()
    assert a.gallery_id == b.gallery_id


def test_gallery_id_changes_with_benchmark_pack_paths():
    a = _valid_gallery(benchmark_pack_paths=["a/BenchmarkPack.json"])
    b = _valid_gallery(benchmark_pack_paths=["b/BenchmarkPack.json"])
    assert a.gallery_id != b.gallery_id


def test_compute_gallery_id_is_pure_and_deterministic():
    first = compute_gallery_id(gallery_name="g", benchmark_pack_paths=["a.json"], verification_ids=["v1"])
    second = compute_gallery_id(gallery_name="g", benchmark_pack_paths=["a.json"], verification_ids=["v1"])
    assert first == second
    assert len(first) == 16


def test_gallery_valid_has_no_errors():
    gallery = _valid_gallery()
    assert gallery.validate() == []
    gallery.validate_or_raise()


def test_gallery_empty_limitations_is_invalid():
    gallery = _valid_gallery(limitations=[])
    errors = gallery.validate()
    assert any("limitations" in e for e in errors)


def test_gallery_empty_provenance_is_invalid():
    gallery = _valid_gallery(provenance="")
    errors = gallery.validate()
    assert any("provenance" in e for e in errors)


def test_gallery_blocked_interpretations_default_non_empty():
    gallery = _valid_gallery()
    assert gallery.blocked_interpretations


def test_gallery_verified_and_failed_pack_ids_separated():
    gallery = _valid_gallery(verified_pack_ids=["p1", "p2"], failed_pack_ids=["p3"])
    assert gallery.verified_pack_ids == ["p1", "p2"]
    assert gallery.failed_pack_ids == ["p3"]


def test_gallery_pack_id_in_both_verified_and_failed_is_invalid():
    gallery = _valid_gallery(verified_pack_ids=["p1"], failed_pack_ids=["p1"])
    errors = gallery.validate()
    assert any("verified_pack_ids and failed_pack_ids" in e for e in errors)


def test_gallery_aggregates_dataset_modality_input_mode():
    gallery = _valid_gallery(dataset_ids=["ds005620", "ds000245"], modalities=["EEG", "fMRI"], input_modes=["builtin_ds005620_cohort_summary"])
    assert gallery.dataset_ids == ["ds005620", "ds000245"]
    assert gallery.modalities == ["EEG", "fMRI"]


def test_gallery_no_claim_scope_or_evidence_level_field():
    gallery = _valid_gallery()
    assert not hasattr(gallery, "claim_scope")
    assert not hasattr(gallery, "evidence_level")


def test_gallery_banned_phrase_in_gallery_name_is_rejected():
    gallery = _valid_gallery(gallery_name="this run confirms diagnosis beyond doubt")
    errors = gallery.validate()
    assert any("banned phrase" in e for e in errors)


# -- BenchmarkGalleryIndexV1 --


def test_gallery_index_to_dict_from_dict_roundtrip():
    idx = _valid_gallery_index(sections_rendered=["Pack table"])
    restored = BenchmarkGalleryIndexV1.from_dict(idx.to_dict())
    assert restored == idx


def test_gallery_index_id_stable_for_identical_inputs():
    a = _valid_gallery_index()
    b = _valid_gallery_index()
    assert a.gallery_index_id == b.gallery_index_id


def test_gallery_index_id_changes_with_gallery_id():
    a = _valid_gallery_index(gallery_id="g1")
    b = _valid_gallery_index(gallery_id="g2")
    assert a.gallery_index_id != b.gallery_index_id


def test_compute_gallery_index_id_is_pure_and_deterministic():
    first = compute_gallery_index_id(gallery_id="g1")
    second = compute_gallery_index_id(gallery_id="g1")
    assert first == second
    assert len(first) == 16


def test_gallery_index_valid_has_no_errors():
    idx = _valid_gallery_index(blocked_interpretations=["not clinical evidence"])
    assert idx.validate() == []


def test_gallery_index_empty_limitations_is_invalid():
    idx = _valid_gallery_index(limitations=[])
    errors = idx.validate()
    assert any("limitations" in e for e in errors)
