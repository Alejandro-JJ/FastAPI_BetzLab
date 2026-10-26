"""Traction Force Microscopy worker processor.

This worker mirrors the Streamlit tool's high-level flow:
1) load before/after TIFF stacks,
2) estimate displacements frame-wise,
3) reconstruct traction-like fields from displacement,
4) write one stack for browser preview + download,
5) render matplotlib plots as downloadable/preview artifacts.
"""
from __future__ import annotations

import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter
import numpy as np
import tifffile
from skimage.registration import optical_flow_ilk, phase_cross_correlation

import storage
from traction_force.displacement import (
    Surface,
    RigidShift,
    dft_displacement,
    elastix_3d,
    elastix_displacement,
    rigid_shift_pcc,
)
from traction_force.force import tract
from worker_base.contracts import ToolContext, ToolResult


def _vector_dimension(field: np.ndarray) -> int:
    arr = np.asarray(field)
    if arr.ndim >= 3 and arr.shape[-1] in (2, 3):
        return int(arr.shape[-1])
    if arr.ndim >= 3 and arr.shape[0] in (2, 3):
        return int(arr.shape[0])
    return 2


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _normalize_dim_mode(value: str) -> str:
    supported = {"xy", "xyt", "xyz", "xyzct"}
    mode = (value or "xyt").lower().strip()
    if mode not in supported:
        raise ValueError(f"Unsupported dimension_mode '{value}'. Expected one of {sorted(supported)}")
    return mode


def _infer_dim_mode(before_raw: np.ndarray, after_raw: np.ndarray) -> str:
    if before_raw.ndim == 2 and after_raw.ndim == 2:
        return "xy"
    if before_raw.ndim == 3 and after_raw.ndim == 2:
        return "xyt"
    if before_raw.ndim == 3 and after_raw.ndim == 3:
        return "xyz"
    if before_raw.ndim == 5 and after_raw.ndim == 3:
        return "xyzct"
    raise ValueError(
        "Unable to infer dimension mode from input shapes "
        f"before={before_raw.shape} after={after_raw.shape}. "
        "Provide 'dimension_mode' explicitly."
    )


def _crop_last_two_dims(arr: np.ndarray, x0: int, y0: int, w: int, h: int) -> np.ndarray:
    return arr[..., y0 : y0 + h, x0 : x0 + w]


def _prepare_inputs(before_raw: np.ndarray, after_raw: np.ndarray, dim_mode: str) -> tuple[np.ndarray, np.ndarray]:
    if dim_mode == "xy":
        if before_raw.ndim != 2:
            raise ValueError("Dimension mode 'xy' expects the before image to be 2D")
        if after_raw.ndim != 2:
            raise ValueError("Dimension mode 'xy' expects the after image to be 2D")
        return before_raw[np.newaxis, ...], after_raw

    if dim_mode == "xyt":
        if before_raw.ndim != 3:
            raise ValueError("Dimension mode 'xyt' expects the before image to be 3D (t, y, x)")
        if after_raw.ndim != 2:
            raise ValueError("Dimension mode 'xyt' expects the after image to be 2D")
        return before_raw, after_raw

    if dim_mode == "xyz":
        if before_raw.ndim != 3 or after_raw.ndim != 3:
            raise ValueError("Dimension mode 'xyz' expects both before and after images to be 3D (z, y, x)")
        return before_raw[np.newaxis, ...], after_raw

    if before_raw.ndim != 5:
        raise ValueError("Dimension mode 'xyzct' expects before image to be 5D (t, z, c, y, x)")
    before_zyx_by_t = before_raw[:, :, 0, :, :]
    if after_raw.ndim != 3:
        raise ValueError("Dimension mode 'xyzct' expects after image to be 3D (z, y, x)")
    return before_zyx_by_t, after_raw


def _normalize_for_flow(frame: np.ndarray) -> np.ndarray:
    frame = frame.astype(np.float32)
    minimum = float(np.min(frame))
    maximum = float(np.max(frame))
    scale = maximum - minimum
    if scale <= 0:
        return np.zeros_like(frame, dtype=np.float32)
    return (frame - minimum) / (scale + 1e-10)


def _elastix3d_fallback(moving: np.ndarray, fixed: np.ndarray) -> np.ndarray:
    shift, _, _ = phase_cross_correlation(fixed, moving, upsample_factor=10)
    displacement = np.zeros((*fixed.shape, 3), dtype=np.float32)
    displacement[..., 0] = shift[0]
    displacement[..., 1] = shift[1]
    displacement[..., 2] = shift[2]
    return displacement


def _field_magnitude(field: np.ndarray) -> np.ndarray:
    arr = np.asarray(field)
    if np.iscomplexobj(arr):
        arr = arr.real

    if arr.ndim >= 3 and arr.shape[-1] in (2, 3):
        return np.sqrt(np.sum(np.square(arr.astype(np.float32)), axis=-1, dtype=np.float32))
    if arr.ndim >= 3 and arr.shape[0] in (2, 3):
        moved = np.moveaxis(arr, 0, -1)
        return np.sqrt(np.sum(np.square(moved.astype(np.float32)), axis=-1, dtype=np.float32))
    return np.abs(arr).astype(np.float32)


def _field_preview(field: np.ndarray, mode: str) -> np.ndarray:
    mode = (mode or "magnitude").strip().lower()
    arr = np.asarray(field)
    if np.iscomplexobj(arr):
        arr = arr.real

    if mode == "magnitude":
        return _field_magnitude(arr)

    if mode == "field":
        if arr.ndim >= 3 and arr.shape[-1] in (2, 3):
            return arr[..., 1].astype(np.float32)
        if arr.ndim >= 3 and arr.shape[0] in (2, 3):
            moved = np.moveaxis(arr, 0, -1)
            return moved[..., 1].astype(np.float32)
        return _field_magnitude(arr)

    magnitude = _field_magnitude(arr)
    if arr.ndim >= 3 and arr.shape[-1] in (2, 3):
        return (0.7 * magnitude + 0.3 * np.abs(arr[..., 1])).astype(np.float32)
    if arr.ndim >= 3 and arr.shape[0] in (2, 3):
        moved = np.moveaxis(arr, 0, -1)
        return (0.7 * magnitude + 0.3 * np.abs(moved[..., 1])).astype(np.float32)
    return magnitude


def _field_quiver_components(field: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    arr = np.asarray(field)
    if np.iscomplexobj(arr):
        arr = arr.real

    if arr.ndim >= 3 and arr.shape[-1] >= 3:
        return arr[..., 2].astype(np.float32), arr[..., 1].astype(np.float32)
    if arr.ndim >= 3 and arr.shape[-1] == 2:
        return arr[..., 1].astype(np.float32), arr[..., 0].astype(np.float32)
    if arr.ndim >= 3 and arr.shape[0] >= 3:
        moved = np.moveaxis(arr, 0, -1)
        return moved[..., 2].astype(np.float32), moved[..., 1].astype(np.float32)
    if arr.ndim >= 3 and arr.shape[0] == 2:
        moved = np.moveaxis(arr, 0, -1)
        return moved[..., 1].astype(np.float32), moved[..., 0].astype(np.float32)
    zero = np.zeros(arr.shape[-2:], dtype=np.float32)
    return zero, zero


def _save_matplotlib_plot(
    field: np.ndarray,
    output_path: Path,
    preview_mode: str,
    stage_name: str,
    colormap: str,
    quiver_stride: int,
    show_scale_bar: bool,
    micrometers_per_vector_pixel: float,
    resolution_scale: float,
    quiver_length_scale: float,
    quiver_size_scale: float,
    value_scale: float = 1.0,
    colorbar_label: str | None = None,
) -> None:
    magnitude = _field_magnitude(field) * max(0.0, float(value_scale))
    if magnitude.ndim != 2:
        raise ValueError("Expected 2D magnitude for matplotlib preview")

    height, width = int(magnitude.shape[0]), int(magnitude.shape[1])
    base_scale = max(1.0, float(resolution_scale))
    adaptive_scale = min(3.0, max(1.5, 1500.0 / max(1, max(height, width))))
    scale = min(4.0, max(base_scale, adaptive_scale))
    mode = (preview_mode or "magnitude").strip().lower()
    # Always render arrows for traction stage so force direction is visible.
    if stage_name == "traction" and mode == "magnitude":
        mode = "both"

    image_px_h = int(round(height * scale))
    image_px_w = int(round(width * scale))
    colorbar_enabled = mode in {"magnitude", "both"}
    cbar_px = max(28, int(round(image_px_w * 0.06))) if colorbar_enabled else 0
    pad_px = 12 if colorbar_enabled else 0

    total_px_w = image_px_w + cbar_px + pad_px
    total_px_h = image_px_h
    dpi = 200
    figure = plt.figure(figsize=(total_px_w / dpi, total_px_h / dpi), dpi=dpi)

    if colorbar_enabled:
        image_width_frac = image_px_w / total_px_w
        pad_frac = pad_px / total_px_w
        cbar_frac = cbar_px / total_px_w
        axes = figure.add_axes([0.0, 0.0, image_width_frac, 1.0])
        cbar_axes = figure.add_axes([image_width_frac + pad_frac, 0.07, cbar_frac, 0.86])
    else:
        axes = figure.add_axes([0.0, 0.0, 1.0, 1.0])
        cbar_axes = None

    axes.set_axis_off()
    axes.set_aspect("equal", adjustable="box")

    image = axes.imshow(magnitude, cmap=colormap, origin="lower", interpolation="nearest")

    if mode in {"field", "both"}:
        u, v = _field_quiver_components(field)
        stride = max(1, int(quiver_stride))
        yy, xx = np.mgrid[0:height:stride, 0:width:stride]
        uu = u[::stride, ::stride]
        vv = v[::stride, ::stride]
        magnitude_uv = np.sqrt(np.square(uu) + np.square(vv)) * max(0.0, float(value_scale))
        max_magnitude = float(np.max(magnitude_uv)) if magnitude_uv.size > 0 else 0.0
        if mode == "both":
            color = "white"
            alpha = 1.0
            c_values = None
        else:
            color = None
            alpha = 1.0
            c_values = magnitude_uv

        size_scale = max(0.1, float(quiver_size_scale))
        quiver_kwargs = {
            "pivot": "middle",
            "angles": "xy",
            "scale_units": "xy",
            "scale": None,
            "width": max(0.0012, 0.0030 * size_scale),
            "headwidth": max(2.5, 4.2 * size_scale),
            "headlength": max(3.2, 5.8 * size_scale),
            "headaxislength": max(2.8, 5.2 * size_scale),
            "minshaft": 2,
            "minlength": 0.6,
            "alpha": alpha,
        }
        length_scale = max(0.05, float(quiver_length_scale))
        if max_magnitude > 0:
            normalize_to_pixels = max(8.0, 0.12 * min(height, width))
            uu = (uu / max_magnitude) * normalize_to_pixels * length_scale
            vv = (vv / max_magnitude) * normalize_to_pixels * length_scale
        else:
            uu = uu * length_scale
            vv = vv * length_scale

        if c_values is None:
            axes.quiver(xx, yy, uu, vv, color=color, **quiver_kwargs)
        else:
            axes.quiver(xx, yy, uu, vv, c_values, cmap=colormap, **quiver_kwargs)

    if colorbar_enabled and cbar_axes is not None:
        # Plain tick labels while values are readable; switch to scientific
        # notation (powers of ten) outside 1e-2..1e3 so Pa values stay legible.
        tick_formatter = ScalarFormatter(useMathText=True)
        tick_formatter.set_powerlimits((-2, 3))
        colorbar = figure.colorbar(image, cax=cbar_axes, orientation="vertical", format=tick_formatter)
        colorbar.outline.set_linewidth(0.8)
        colorbar.ax.tick_params(labelsize=7, length=2, width=0.8)
        if colorbar_label:
            colorbar.set_label(colorbar_label, fontsize=8)

    if show_scale_bar and micrometers_per_vector_pixel > 0:
        target_um = 10.0
        length_px = max(8, min(int(width * 0.35), int(round(target_um / micrometers_per_vector_pixel))))
        label_um = length_px * micrometers_per_vector_pixel
        x0 = int(width * 0.05)
        y0 = int(height * 0.08)
        axes.plot([x0, x0 + length_px], [y0, y0], color="white", linewidth=2.0, solid_capstyle="butt")
        axes.text(x0, y0 + max(3, int(height * 0.018)), f"{label_um:.1f} µm", color="white", fontsize=7, ha="left", va="bottom")

    figure.savefig(output_path, dpi=dpi, facecolor="white", edgecolor="white")
    plt.close(figure)


def _resolve_elastix3d_parameter_file(context: ToolContext, params: dict) -> str | None:
    custom_path = params.get("elastix3d_parameter_file")
    candidates: list[Path] = []
    if isinstance(custom_path, str) and custom_path.strip():
        candidates.append(Path(custom_path.strip()))
    candidates.extend(
        [
            context.workdir / "bspline_tfm.txt",
            Path("/app/tools/traction_force/bspline_tfm.txt"),
            Path("tools/traction_force/bspline_tfm.txt"),
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def process(input_path: Path, context: ToolContext) -> ToolResult:
    params = context.params
    started = time.perf_counter()

    after_object_key = params.get("after_object_key")
    if not isinstance(after_object_key, str) or not after_object_key:
        raise ValueError("Missing required parameter: after_object_key")

    after_path = context.workdir / Path(after_object_key).name
    storage.download_to_path(after_object_key, after_path)

    before_raw = tifffile.imread(input_path)
    after_raw = tifffile.imread(after_path)

    raw_dim_mode = params.get("dimension_mode")
    if raw_dim_mode is None or str(raw_dim_mode).strip() == "":
        dim_mode = _infer_dim_mode(before_raw, after_raw)
    else:
        dim_mode = _normalize_dim_mode(str(raw_dim_mode))

    displacement_method = str(params.get("displacement_method", "dft")).strip().lower()
    half_window_size = int(params.get("half_window_size", 10))
    step_size = int(params.get("step_size", 10))
    mue2pix = float(params.get("mue2pix", 0.0772))
    e = float(params.get("E", 1200))
    nu = float(params.get("nu", 0.49))
    run_traction = _as_bool(params.get("run_traction", True))
    radius = int(params.get("optical_flow_radius", 30))
    alpha0 = float(params.get("alpha0", 1e-15))
    gel_height = float(params.get("h", 60))
    z = float(params.get("z", 60))
    workflow_stage = str(params.get("workflow_stage", "traction")).strip().lower()
    preview_mode = str(params.get("preview_mode", "magnitude")).strip().lower()

    plot_colormap = str(params.get("plot_colormap", "jet")).strip().lower()
    plot_quiver_stride = int(params.get("quiver_stride", 1))
    show_scale_bar = _as_bool(params.get("show_scale_bar", True))
    plot_resolution_scale = float(params.get("plot_resolution_scale", 2.5))
    plot_quiver_length_scale = float(params.get("plot_quiver_length_scale", 1.0))
    plot_quiver_size_scale = float(params.get("plot_quiver_size_scale", 1.0))

    before_data, after_data = _prepare_inputs(before_raw, after_raw, dim_mode)

    if _as_bool(params.get("crop_enabled", False)):
        x0 = int(params.get("crop_x0", 0))
        y0 = int(params.get("crop_y0", 0))
        w = int(params.get("crop_w", before_data.shape[-1] - x0))
        h_crop = int(params.get("crop_h", before_data.shape[-2] - y0))
        before_data = _crop_last_two_dims(before_data, x0, y0, w, h_crop)
        after_data = _crop_last_two_dims(after_data, x0, y0, w, h_crop)

    if _as_bool(params.get("rigid_align_crop", False)) and dim_mode in {"xy", "xyt"}:
        fixed_2d_align = np.asarray(after_data)
        if before_data.shape[0] > 0:
            uy, ux = RigidShift(np.asarray(before_data[0]), fixed_2d_align, max(8, fixed_2d_align.shape[0] // 5))
            uy, ux = int(round(uy)), int(round(ux))
            refined_uy, refined_ux = rigid_shift_pcc(np.roll(fixed_2d_align, shift=(-uy, -ux), axis=(0, 1)), np.asarray(before_data[0]))
            total_y = int(round(uy + refined_uy))
            total_x = int(round(ux + refined_ux))
            after_data = np.roll(fixed_2d_align, shift=(-total_y, -total_x), axis=(0, 1))

    displacement_fields: list[np.ndarray] = []
    displacement_errors: list[np.ndarray] = []
    method_notes: list[str] = []

    if dim_mode in {"xy", "xyt"}:
        fixed_2d = np.asarray(after_data)
        for frame in before_data:
            moving_2d = np.asarray(frame)
            if displacement_method == "optical_flow":
                dis = optical_flow_ilk(
                    _normalize_for_flow(moving_2d),
                    _normalize_for_flow(fixed_2d),
                    radius=radius,
                )
                displacement_fields.append(np.stack([dis[1], dis[0]], axis=-1).astype(np.float32))
            elif displacement_method in {"dft", "elastix"}:
                if displacement_method == "dft":
                    dis, err, _positions = dft_displacement(
                        moving_2d,
                        fixed_2d,
                        half_window_size,
                        step_size,
                    )
                    displacement_fields.append(dis.astype(np.float32))
                    displacement_errors.append(err.astype(np.float32))
                else:
                    try:
                        dis = elastix_displacement(
                            fixed_2d,
                            moving_2d,
                            half_window_size,
                            step_size,
                        )
                        displacement_fields.append(np.asarray(dis).astype(np.float32))
                    except Exception as elastix_error:
                        method_notes.append(
                            f"elastix_displacement failed on a frame ({type(elastix_error).__name__}); used dft_displacement fallback"
                        )
                        dis, err, _positions = dft_displacement(
                            moving_2d,
                            fixed_2d,
                            half_window_size,
                            step_size,
                        )
                        displacement_fields.append(dis.astype(np.float32))
                        displacement_errors.append(err.astype(np.float32))
            else:
                raise ValueError("For xy/xyt, displacement_method must be one of: dft, elastix, optical_flow")

    elif dim_mode in {"xyz", "xyzct"}:
        if displacement_method != "elastix3d":
            raise ValueError("For xyz/xyzct, displacement_method must be elastix3d")
        fixed_3d = np.asarray(after_data)
        parameter_file = _resolve_elastix3d_parameter_file(context, params)
        if parameter_file is None:
            method_notes.append("Missing bspline_tfm.txt; elastix3d fallback to rigid phase correlation")
            for frame_3d in before_data:
                displacement_fields.append(_elastix3d_fallback(np.asarray(frame_3d), fixed_3d))
        else:
            surface_index = int(params.get("surface_index", 9))
            if dim_mode == "xyzct":
                try:
                    surface_index = Surface(fixed_3d)
                except Exception:
                    surface_index = int(params.get("surface_index", 9))
            for frame_3d in before_data:
                try:
                    displacement_fields.append(
                        np.asarray(
                            elastix_3d(
                                np.asarray(frame_3d),
                                fixed_3d,
                                parameter_file,
                                step_size,
                                step_size,
                                surface_index,
                            )
                        ).astype(np.float32)
                    )
                except Exception as elastix3d_error:
                    method_notes.append(
                        f"elastix_3d failed on a frame ({type(elastix3d_error).__name__}); used rigid 3D fallback"
                    )
                    displacement_fields.append(_elastix3d_fallback(np.asarray(frame_3d), fixed_3d))
    else:
        raise ValueError(f"Unsupported dimension mode '{dim_mode}'")

    traction_fields: list[np.ndarray] = []
    if run_traction:
        for dis in displacement_fields:
            dis_scaled = dis * mue2pix
            d_eff = _vector_dimension(dis_scaled)
            if displacement_method == "optical_flow":
                traction_result = tract(dis_scaled, e, nu, mue2pix, alpha0, gel_height, z, d_eff)
            else:
                traction_result = tract(dis_scaled, e, nu, mue2pix, alpha0, gel_height, z, d_eff, [True, step_size])
            traction_fields.append(np.asarray(traction_result["tractions"]).real.astype(np.float32))

    fields_for_preview = traction_fields if run_traction else displacement_fields
    if len(fields_for_preview) == 1:
        vector_stack = np.asarray(fields_for_preview[0]).astype(np.float32)
    else:
        vector_stack = np.stack(fields_for_preview, axis=0).astype(np.float32)

    vector_path = context.workdir / f"tfm_vectors_{input_path.stem}.npy"
    np.save(vector_path, vector_stack)

    vector_pixel_step = step_size if displacement_method in {"dft", "elastix", "elastix3d"} else 1
    micrometers_per_vector_pixel = mue2pix * max(1, vector_pixel_step)

    matplotlib_artifacts: dict[str, Path] = {}

    def _render_stage_plots(
        stage_name: str,
        fields: list[np.ndarray],
        um_per_pixel: float,
        value_scale: float,
        colorbar_label: str,
    ) -> None:
        for slice_index, field in enumerate(fields):
            plot_path = context.workdir / f"tfm_plot_{stage_name}_{input_path.stem}_slice_{slice_index:04d}.png"
            _save_matplotlib_plot(
                field,
                plot_path,
                preview_mode=preview_mode,
                stage_name=stage_name,
                colormap=plot_colormap,
                quiver_stride=max(1, plot_quiver_stride),
                show_scale_bar=show_scale_bar,
                micrometers_per_vector_pixel=um_per_pixel,
                resolution_scale=plot_resolution_scale,
                quiver_length_scale=plot_quiver_length_scale,
                quiver_size_scale=plot_quiver_size_scale,
                value_scale=value_scale,
                colorbar_label=colorbar_label,
            )
            matplotlib_artifacts[f"matplotlib_{stage_name}_slice_{slice_index:04d}"] = plot_path
            if slice_index == 0:
                matplotlib_artifacts[f"matplotlib_{stage_name}_plot"] = plot_path

    # Displacement is plotted in micrometers (raw fields are in pixels,
    # exactly like the Streamlit tool's `dis * mue2pix`); traction in Pascals.
    if displacement_fields:
        _render_stage_plots(
            "displacement",
            displacement_fields,
            micrometers_per_vector_pixel,
            value_scale=mue2pix,
            colorbar_label="µm",
        )

    if traction_fields:
        _render_stage_plots(
            "traction",
            traction_fields,
            micrometers_per_vector_pixel,
            value_scale=1.0,
            colorbar_label="Pa",
        )

    generic_stage = "traction" if run_traction and traction_fields else "displacement"
    if f"matplotlib_{generic_stage}_plot" in matplotlib_artifacts:
        matplotlib_artifacts["matplotlib_plot"] = matplotlib_artifacts[f"matplotlib_{generic_stage}_plot"]
    for slice_index in range(len(fields_for_preview)):
        source = f"matplotlib_{generic_stage}_slice_{slice_index:04d}"
        if source in matplotlib_artifacts:
            matplotlib_artifacts[f"matplotlib_plot_slice_{slice_index:04d}"] = matplotlib_artifacts[source]

    preview_frames = [_field_preview(field, preview_mode) for field in fields_for_preview]
    if len(preview_frames) == 1:
        result_stack = preview_frames[0]
    else:
        result_stack = np.stack(preview_frames, axis=0)

    result_path = context.workdir / f"tfm_result_{input_path.stem}.tif"
    tifffile.imwrite(result_path, result_stack.astype(np.float32))

    metadata = {
        "job_id": context.job_id,
        "source_file": input_path.name,
        "reference_file": after_path.name,
        "operation": "TractionForceMicroscopy",
        "parameters": params,
        "workflow_stage": workflow_stage,
        "dimension_mode": dim_mode,
        "displacement_method": displacement_method,
        "displacement_frames": len(displacement_fields),
        "displacement_error_frames": len(displacement_errors),
        "traction_frames": len(traction_fields),
        "preview": "traction" if run_traction else "displacement",
        "preview_mode": preview_mode,
        "plot_colormap": plot_colormap,
        "plot_quiver_length_scale": plot_quiver_length_scale,
        "plot_quiver_size_scale": plot_quiver_size_scale,
        "vector_field_unit": "Pa" if run_traction else "pixels",
        "vector_field_scale_hint": 1.0 if run_traction else mue2pix,
        "matplotlib_plot_count": len(fields_for_preview),
        "notes": method_notes,
        "duration_seconds": round(time.perf_counter() - started, 2),
    }

    artifacts = {"vector_fields": vector_path, **matplotlib_artifacts}

    return ToolResult(
        result_path=result_path,
        metadata=metadata,
        artifacts=artifacts,
        render_mode="grayscale",
    )
