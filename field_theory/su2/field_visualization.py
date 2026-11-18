"""Optional visualization of static SU(2) quaternion-field slices.

Matplotlib is imported only when plotting is requested. Coordinates are centered
index coordinates derived from shape and spacing; SU2GridField carries no
separate world-coordinate origin.
"""
from __future__ import annotations

from numbers import Integral

import numpy as np

from .field import SU2GridField


_AXIS_NAMES = ("x", "y", "z")
_COMPONENT_NAMES = ("n0", "n1", "n2", "n3")


def plot_su2_field_components(
    field: SU2GridField,
    *,
    axis: int = 2,
    index: int | None = None,
    figsize: tuple[float, float] = (10.0, 8.0),
):
    """Plot all four real quaternion components on one Cartesian grid slice.

    The plane is normal to `axis`; `index=None` selects its middle sample.
    Explicit indices are zero-based. The returned pair is (figure, 2x2 axes).
    The shared color scale is fixed to [-1, 1], as required by the unit-field
    contract. Spatial coordinates are centered index*spacing coordinates, since
    SU2GridField does not store a physical origin. This is a display convention,
    not a claim about absolute coordinates. No charge or topological invariant
    is computed.
    """
    if not isinstance(field, SU2GridField):
        raise ValueError("field must be an SU2GridField")
    if isinstance(axis, (bool, np.bool_)) or not isinstance(axis, Integral):
        raise ValueError("axis must be an integer from 0 through 2")
    axis = int(axis)
    if axis not in range(3):
        raise ValueError("axis must be an integer from 0 through 2")

    shape = field.components.shape[:3]
    if index is None:
        index = shape[axis] // 2
    elif isinstance(index, (bool, np.bool_)) or not isinstance(index, Integral):
        raise ValueError("index must be an integer within the selected axis")
    index = int(index)
    if index < 0 or index >= shape[axis]:
        raise ValueError("index must be within the selected axis")

    if (
        not isinstance(figsize, (tuple, list))
        or len(figsize) != 2
        or any(isinstance(value, (bool, np.bool_)) for value in figsize)
    ):
        raise ValueError("figsize must contain two positive finite numbers")
    try:
        width, height = (float(value) for value in figsize)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("figsize must contain two positive finite numbers") from exc
    if not np.isfinite((width, height)).all() or width <= 0.0 or height <= 0.0:
        raise ValueError("figsize must contain two positive finite numbers")

    # Keep this dependency optional for callers that only use field operations.
    import matplotlib.pyplot as plt

    coordinates = tuple(
        (np.arange(size, dtype=np.float64) - (size - 1) / 2.0) * spacing
        for size, spacing in zip(shape, field.spacing)
    )
    plane_axes = [candidate for candidate in range(3) if candidate != axis]
    vertical_axis, horizontal_axis = plane_axes
    horizontal_spacing = field.spacing[horizontal_axis]
    vertical_spacing = field.spacing[vertical_axis]
    extent = (
        float(coordinates[horizontal_axis][0] - horizontal_spacing / 2.0),
        float(coordinates[horizontal_axis][-1] + horizontal_spacing / 2.0),
        float(coordinates[vertical_axis][0] - vertical_spacing / 2.0),
        float(coordinates[vertical_axis][-1] + vertical_spacing / 2.0),
    )

    sliced = np.take(field.components, index, axis=axis)
    fig, axes = plt.subplots(2, 2, figsize=(width, height), squeeze=False)
    images = []
    for component, ax in enumerate(axes.flat):
        image = ax.imshow(
            sliced[..., component],
            origin="lower",
            interpolation="nearest",
            aspect="auto",
            extent=extent,
            cmap="coolwarm",
            vmin=-1.0,
            vmax=1.0,
        )
        images.append(image)
        ax.set_title(_COMPONENT_NAMES[component])
        ax.set_xlabel(f"{_AXIS_NAMES[horizontal_axis]} ({field.length_unit})")
        ax.set_ylabel(f"{_AXIS_NAMES[vertical_axis]} ({field.length_unit})")

    fig.suptitle(
        f"SU(2) field slice normal to {_AXIS_NAMES[axis]} at index {index}"
    )
    fig.colorbar(images[0], ax=list(axes.flat), label="quaternion component")
    fig.tight_layout()
    return fig, axes
