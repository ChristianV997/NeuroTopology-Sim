import numpy as np
import pytest

import matplotlib
matplotlib.use("Agg", force=True)

from field_theory.su2 import SU2GridField, hedgehog
from field_theory.su2.field_visualization import plot_su2_field_components


def _periodic_field():
    shape = (3, 4, 5)
    i, j, k = np.indices(shape, dtype=np.float64)
    raw = np.stack(
        (1.0 + i, 1.0 + 2.0 * j, 1.0 + k, 1.0 + i + j + k),
        axis=-1,
    )
    values = raw / np.linalg.norm(raw, axis=-1, keepdims=True)
    return SU2GridField(
        values,
        spacing=(0.5, 0.25, 0.1),
        boundary="periodic",
        length_unit="cm",
    )


def test_four_component_slice_uses_selected_index_shared_scale_and_spacing_labels():
    field = _periodic_field()
    original = field.components.tobytes()
    axis, index = 1, 2

    fig, axes = plot_su2_field_components(field, axis=axis, index=index)
    try:
        assert axes.shape == (2, 2)
        assert len(fig.axes) == 5  # four panels plus one shared colorbar
        vertical_axis, horizontal_axis = 0, 2
        plane = np.take(field.components, index, axis=axis)
        coordinates = tuple(
            (np.arange(size) - (size - 1) / 2.0) * step
            for size, step in zip(field.components.shape[:3], field.spacing)
        )
        horizontal_spacing = field.spacing[horizontal_axis]
        vertical_spacing = field.spacing[vertical_axis]
        expected_extent = (
            coordinates[horizontal_axis][0] - horizontal_spacing / 2.0,
            coordinates[horizontal_axis][-1] + horizontal_spacing / 2.0,
            coordinates[vertical_axis][0] - vertical_spacing / 2.0,
            coordinates[vertical_axis][-1] + vertical_spacing / 2.0,
        )

        for component, ax in enumerate(axes.flat):
            image = ax.images[0]
            image_values = np.asarray(image.get_array())
            np.testing.assert_array_equal(image_values, plane[..., component])
            assert image.get_clim() == (-1.0, 1.0)
            assert image.origin == "lower"
            extent = image.get_extent()
            assert extent == pytest.approx(expected_extent)
            rendered_x_centers = extent[0] + (
                np.arange(image_values.shape[1]) + 0.5
            ) * (extent[1] - extent[0]) / image_values.shape[1]
            rendered_y_centers = extent[2] + (
                np.arange(image_values.shape[0]) + 0.5
            ) * (extent[3] - extent[2]) / image_values.shape[0]
            np.testing.assert_allclose(
                rendered_x_centers, coordinates[horizontal_axis], atol=1e-15
            )
            np.testing.assert_allclose(
                rendered_y_centers, coordinates[vertical_axis], atol=1e-15
            )
            assert ax.get_title() == f"n{component}"
            assert ax.get_xlabel() == "z (cm)"
            assert ax.get_ylabel() == "x (cm)"
        assert field.components.tobytes() == original
    finally:
        import matplotlib.pyplot as plt
        plt.close(fig)


def test_fixed_vacuum_midplane_defaults_to_center_and_does_not_mutate():
    field = hedgehog((5, 5, 5), radius=0.8, spacing=(0.5, 0.5, 0.5))
    original = field.components.tobytes()

    fig, axes = plot_su2_field_components(field)
    try:
        assert "z at index 2" in fig._suptitle.get_text()
        np.testing.assert_array_equal(
            np.asarray(axes[0, 0].images[0].get_array()),
            field.components[:, :, 2, 0],
        )
        assert field.components.tobytes() == original
    finally:
        import matplotlib.pyplot as plt
        plt.close(fig)


@pytest.mark.parametrize("axis", [True, -1, 3, 1.5, "x", None])
def test_invalid_axis_is_rejected(axis):
    with pytest.raises(ValueError, match="axis"):
        plot_su2_field_components(_periodic_field(), axis=axis)


@pytest.mark.parametrize("index", [True, -1, 4, 1.5, "2"])
def test_invalid_selected_slice_is_rejected(index):
    with pytest.raises(ValueError, match="index"):
        plot_su2_field_components(_periodic_field(), axis=1, index=index)


@pytest.mark.parametrize("figsize", [(0.0, 2.0), (1.0,), (float("nan"), 2.0), (True, 2.0)])
def test_invalid_figure_size_is_rejected(figsize):
    with pytest.raises(ValueError, match="figsize"):
        plot_su2_field_components(_periodic_field(), figsize=figsize)


def test_non_field_input_is_rejected():
    with pytest.raises(ValueError, match="SU2GridField"):
        plot_su2_field_components(np.zeros((2, 2, 2, 4)))
