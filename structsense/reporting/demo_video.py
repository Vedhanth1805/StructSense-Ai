"""Reproducible presentation video using the existing analysis and geometry modules.

The rendered building is parametric and illustrative. It does not simulate
structural displacement, cracking, or finite-element behavior.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .structure_model import build_frame


DEMO_TITLE = "StructSense AI — Structural Risk Demonstration"
DEMO_END_TITLE = "StructSense AI — Structural Risk Screening and Decision Support"
FRAME_HOLD_SECONDS = 4

# All values are within the current BuildingStressEnv.PARAM_BOUNDS ranges.
ORIGINAL_PARAMETERS: Dict[str, float] = {
    "concrete_grade": 30.0, "steel_grade": 500.0,
    "column_width_mm": 450.0, "column_depth_mm": 600.0,
    "num_floors": 5.0, "floor_load_kn_m2": 5.0,
    "soil_bearing_capacity_kn_m2": 200.0, "foundation_depth_m": 1.5,
    "seismic_zone": 2.0, "wind_speed_kmph": 100.0,
    "rainfall_mm_annual": 800.0, "building_age_years": 10.0,
    "shear_wall_present": 1.0, "foundation_type": 1.0,
    "column_reinforcement_ratio": 0.02, "beam_depth_mm": 500.0,
    "slab_thickness_mm": 150.0, "location_risk_index": 0.3,
}
MODIFIED_PARAMETERS: Dict[str, float] = {
    **ORIGINAL_PARAMETERS,
    "concrete_grade": 20.0, "steel_grade": 415.0,
    "column_width_mm": 300.0, "column_depth_mm": 450.0,
    "floor_load_kn_m2": 8.0, "beam_depth_mm": 350.0,
    "slab_thickness_mm": 100.0,
}

PARAMETER_STEPS = (
    ("concrete_grade", "Concrete grade", "M{}", "Material strength updated"),
    ("steel_grade", "Reinforcing steel", "Fe{}", "Material strength updated"),
    ("column_width_mm", "Column width", "{} mm", "Column sections updated"),
    ("column_depth_mm", "Column depth", "{} mm", "Column sections updated"),
    ("beam_depth_mm", "Beam depth", "{} mm", "Beam sections updated"),
    ("slab_thickness_mm", "Slab thickness", "{} mm", "Slab thickness updated"),
    ("floor_load_kn_m2", "Floor load", "{} kN/m²", "Load condition increased"),
)


def _pretty(key: str, value: float) -> str:
    spec = next((item for item in PARAMETER_STEPS if item[0] == key), None)
    return spec[2].format(int(value) if float(value).is_integer() else value) if spec else str(value)


def _parameter_rows(parameters: Dict[str, float]) -> list[tuple[str, str]]:
    return [
        ("Concrete", _pretty("concrete_grade", parameters["concrete_grade"])),
        ("Steel", _pretty("steel_grade", parameters["steel_grade"])),
        ("Column section", "%s × %s mm" % (int(parameters["column_width_mm"]), int(parameters["column_depth_mm"]))),
        ("Beam depth", _pretty("beam_depth_mm", parameters["beam_depth_mm"])),
        ("Slab thickness", _pretty("slab_thickness_mm", parameters["slab_thickness_mm"])),
        ("Floor load", _pretty("floor_load_kn_m2", parameters["floor_load_kn_m2"])),
        ("Floors", str(int(parameters["num_floors"]))),
    ]


def _cuboid(ax: Any, x: float, y: float, z: float, dx: float, dy: float, dz: float,
            color: str, alpha: float = 1.0) -> None:
    """Draw a rectangular structural member using explicit parametric dimensions."""
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    corners = [(x, y, z), (x+dx, y, z), (x+dx, y+dy, z), (x, y+dy, z),
               (x, y, z+dz), (x+dx, y, z+dz), (x+dx, y+dy, z+dz), (x, y+dy, z+dz)]
    faces = [[corners[i] for i in face] for face in (
        (0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
        (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))]
    ax.add_collection3d(Poly3DCollection(faces, facecolors=color, edgecolors="#55708a",
                                         linewidths=0.45, alpha=alpha))


def _draw_building(ax: Any, parameters: Dict[str, float], changed_key: Optional[str] = None) -> None:
    """Draw a simple 2-bay, multi-floor building with scale tied to parameters."""
    floors = int(parameters["num_floors"])
    span, story = 4.0, 2.5
    col_w = 0.16 * parameters["column_width_mm"] / 450.0
    col_d = 0.16 * parameters["column_depth_mm"] / 600.0
    beam_h = 0.25 * parameters["beam_depth_mm"] / 500.0
    slab_h = 0.12 * parameters["slab_thickness_mm"] / 150.0
    xlines, ylines = (0.0, span, 2*span), (0.0, span, 2*span)

    for level in range(floors):
        for x in xlines:
            for y in ylines:
                _cuboid(ax, x-col_w/2, y-col_d/2, level*story, col_w, col_d, story,
                        "#e99457" if changed_key in ("column_width_mm", "column_depth_mm") else "#4f9ec7")
    for level in range(1, floors+1):
        z = level*story
        for y in ylines:
            for x in (0.0, span):
                _cuboid(ax, x, y-beam_h/2, z-beam_h/2, span, beam_h, beam_h,
                        "#e99457" if changed_key == "beam_depth_mm" else "#79c4ac")
        for x in xlines:
            for y in (0.0, span):
                _cuboid(ax, x-beam_h/2, y, z-beam_h/2, beam_h, span, beam_h,
                        "#e99457" if changed_key == "beam_depth_mm" else "#79c4ac")
        _cuboid(ax, 0, 0, z-slab_h, 2*span, 2*span, slab_h,
                "#92a7bb" if changed_key != "slab_thickness_mm" else "#e99457", alpha=0.23)

    ax.set_xlim(-1.0, 2*span+1.0)
    ax.set_ylim(-1.0, 2*span+1.0)
    ax.set_zlim(0, floors*story+1.0)
    ax.set_box_aspect((1, 1, max(0.6, floors*story/(2*span))))
    ax.view_init(elev=23, azim=-54)
    ax.set_axis_off()
    ax.set_title("PARAMETRIC 3D MODEL  ·  NOT FEA", color="#afc3d8", fontsize=10, pad=2)


def _render_frame(path: Path, title: str, subtitle: str,
                  parameters: Dict[str, float], stage: str,
                  analysis: Optional[Dict[str, Any]] = None,
                  changed_key: Optional[str] = None,
                  comparison: bool = False,
                  before_analysis: Optional[Dict[str, Any]] = None) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(12.8, 7.2), dpi=100, facecolor="#101a2a")
    fig.text(0.055, 0.92, title, color="#f4f7fb", fontsize=21, weight="bold")
    fig.text(0.057, 0.865, subtitle, color="#a9bdd2", fontsize=11)
    ax = fig.add_axes([0.035, 0.105, 0.57, 0.70], projection="3d", facecolor="#101a2a")
    _draw_building(ax, parameters, changed_key)
    fig.text(0.66, 0.78, stage.upper(), color="#7bd7be", fontsize=10, weight="bold")
    fig.text(0.66, 0.725, "STRUCTURAL PARAMETERS", color="#f4f7fb", fontsize=13, weight="bold")

    rows = _parameter_rows(parameters)
    if comparison:
        originals = _parameter_rows(ORIGINAL_PARAMETERS)
        modified = _parameter_rows(MODIFIED_PARAMETERS)
        rows = [(label, "%s   →   %s" % (before, after))
                for (label, before), (_, after) in zip(originals, modified)]
    for index, (label, value) in enumerate(rows):
        y = 0.675 - index*0.047
        fig.text(0.66, y, label, color="#91a8bd", fontsize=10)
        fig.text(0.84, y, value, color="#f4f7fb", fontsize=10, weight="bold")

    if analysis:
        base_y = 0.31 if not comparison else 0.34
        fig.text(0.66, base_y, "EXISTING ANALYSIS PIPELINE", color="#f4f7fb", fontsize=12, weight="bold")
        fig.text(0.66, base_y-0.055,
                 "Risk: %s / 100 · %s" % (analysis["overall_risk_score"], analysis["risk_label"]),
                 color="#ffcb7b", fontsize=12, weight="bold")
        if comparison and before_analysis:
            fig.text(0.66, base_y-0.09,
                     "Before risk: %s / 100 · %s" % (
                         before_analysis["overall_risk_score"], before_analysis["risk_label"]),
                     color="#a9bdd2", fontsize=10)
            scenario_top = base_y-0.135
        else:
            scenario_top = base_y-0.105
        scenario_items = list(analysis.get("scenario_results", {}).items())
        for i, (name, result) in enumerate(scenario_items[:5]):
            verdict = "PASS" if result.get("passed") is True else "REVIEW" if result.get("passed") is False else "N/A"
            color = "#7bd7be" if verdict == "PASS" else "#ff9a83"
            fig.text(0.66, scenario_top-i*0.027, "%s  ·  %s" % (verdict, name), color=color, fontsize=7)
    if changed_key:
        fig.text(0.66, 0.20, "UPDATED: " + changed_key.replace("_", " ").upper(),
                 color="#ffcb7b", fontsize=10, weight="bold")
    fig.text(0.055, 0.055,
             "Illustrative parametric geometry only. No displacement simulation or validated FEA is performed.",
             color="#94a8bc", fontsize=8)
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)


def _find_ffmpeg(prefer_mp4: bool) -> Optional[str]:
    """Find system FFmpeg or the standalone binary bundled by imageio-ffmpeg."""
    if not prefer_mp4:
        return None
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        return bundled if Path(bundled).is_file() else None
    except (ImportError, OSError, RuntimeError):
        return None


def generate_demo_video(output_dir: str | Path, prefer_mp4: bool = True) -> Path:
    """Run both configurations through existing analysis and export MP4/GIF.

    MP4 is selected when FFmpeg is installed. Otherwise a presentation-length GIF
    is generated. Returns the absolute exported artifact path.
    """
    from analysis.service import StructuralAnalysisService
    from environment.building_env import PARAM_KEYS

    if set(ORIGINAL_PARAMETERS) != set(PARAM_KEYS) or set(MODIFIED_PARAMETERS) != set(PARAM_KEYS):
        raise RuntimeError("Demo configuration does not match the supported analysis parameter schema")
    build_frame(ORIGINAL_PARAMETERS)
    build_frame(MODIFIED_PARAMETERS)
    service = StructuralAnalysisService()
    before_result = service.analyze(dict(ORIGINAL_PARAMETERS))
    after_result = service.analyze(dict(MODIFIED_PARAMETERS))

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    ffmpeg = _find_ffmpeg(prefer_mp4)
    suffix = ".mp4" if ffmpeg else ".gif"
    output_path = destination / ("structsense-structural-risk-demo" + suffix)

    states = [(dict(ORIGINAL_PARAMETERS), "ORIGINAL CONFIGURATION", None)]
    changed = dict(ORIGINAL_PARAMETERS)
    for key, label, fmt, description in PARAMETER_STEPS:
        changed[key] = MODIFIED_PARAMETERS[key]
        states.append((dict(changed), "%s  ·  %s" % (label.upper(), description), key))
    states.append((dict(MODIFIED_PARAMETERS), "MODIFIED / STRESS CONFIGURATION", None))

    with tempfile.TemporaryDirectory(prefix="structsense-demo-") as temp_name:
        temp = Path(temp_name)
        frames: list[Path] = []
        def add_frame(title: str, subtitle: str, params: Dict[str, float], stage: str,
                      result: Optional[Dict[str, Any]] = None, key: Optional[str] = None,
                      compare: bool = False,
                      before_result: Optional[Dict[str, Any]] = None) -> None:
            target = temp / ("frame_%04d.png" % len(frames))
            _render_frame(target, title, subtitle, params, stage, result, key, compare, before_result)
            frames.append(target)

        add_frame(DEMO_TITLE, "A fixed, reproducible scenario using supported StructSense parameters",
                  ORIGINAL_PARAMETERS, "DEMO OVERVIEW")
        for params, stage, key in states:
            add_frame("Parameter change → 3D model update",
                      "Geometry responds to the current parameter set; no simulated damage is shown",
                      params, stage, key=key)
        add_frame("Actual structural screening", "Modified parameters sent to the existing analysis service",
                  MODIFIED_PARAMETERS, "ANALYSIS RESULT", after_result)
        add_frame("BEFORE  vs  AFTER  vs  ANALYSIS",
                  "Original and modified values are compared with the actual implemented checks",
                  MODIFIED_PARAMETERS, "COMPARISON", after_result, compare=True,
                  before_result=before_result)
        add_frame(DEMO_END_TITLE, "Structural Risk Screening and Decision Support",
                  MODIFIED_PARAMETERS, "END", after_result)

        # Keep each presentation state on screen long enough to read. The PNG
        # sequence is expanded into repeated frames rather than relying on a
        # variable-frame-rate MP4, which some presentation players handle poorly.
        video_frames = temp / "video_frames"
        video_frames.mkdir()
        frame_number = 0
        for frame in frames:
            for _ in range(FRAME_HOLD_SECONDS):
                sequence_frame = video_frames / ("frame_%04d.png" % frame_number)
                shutil.copyfile(frame, sequence_frame)
                frame_number += 1

        encoded_mp4 = False
        if ffmpeg:
            command = [ffmpeg, "-y", "-loglevel", "error", "-framerate", "1", "-i",
                       str(video_frames / "frame_%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                       "-movflags", "+faststart", str(output_path)]
            try:
                subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
                encoded_mp4 = output_path.is_file() and output_path.stat().st_size > 0
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                # Some FFmpeg builds omit libx264. The presentation remains
                # usable as a GIF when MP4 encoding is unavailable.
                encoded_mp4 = False
        if not encoded_mp4:
            output_path = destination / "structsense-structural-risk-demo.gif"
            from PIL import Image
            images = [Image.open(frame).convert("RGB") for frame in frames]
            try:
                images[0].save(output_path, save_all=True, append_images=images[1:],
                               duration=FRAME_HOLD_SECONDS * 1000, loop=0, optimize=True)
            finally:
                for image in images:
                    image.close()
    return output_path.resolve()
