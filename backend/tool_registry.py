"""
Tool registry: the single place that lists every analysis tool in the platform.

This module is the integration point a new developer touches when adding a
tool. The frontend dashboard, the run endpoint, and the job scheduler all read
this registry instead of hardcoding tool names, so adding a tool here is
usually enough to make it appear in the UI and be dispatchable.

See docs/ADDING_A_NEW_TOOL.md for the full walkthrough.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ToolParameter:
    """One numeric parameter a tool accepts, used to auto-generate the UI form."""
    name: str
    label: str
    default: float
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    step: float = 1


@dataclass(frozen=True)
class Tool:
    """Metadata describing one analysis tool available in the toolbox."""
    id: str
    name: str
    description: str
    order: int
    # Whether this tool has a working worker image it can be dispatched to.
    enabled: bool
    # Docker image the scheduler starts for one job. Ignored while disabled.
    worker_image: Optional[str] = None
    parameters: tuple[ToolParameter, ...] = field(default_factory=tuple)
    accepted_extensions: tuple[str, ...] = (".tif", ".tiff")


# Add one Tool(...) entry per analysis tool. Order controls dashboard position.
TOOLS: tuple[Tool, ...] = (
    Tool(
        id="beadbuddy",
        name="BeadBuddy",
        description="Bead segmentation and analysis for 3D TIFF stacks.",
        order=1,
        enabled=True,
        worker_image="beadbuddy-worker:latest",
        parameters=(
            ToolParameter("timepoint", "Timepoint", 0, 0, 1000, 1),
            ToolParameter("backg_r", "Background radius", 20, 0, 100, 1),
            ToolParameter("threshold", "Threshold", 200, 0, 65535, 1),
            ToolParameter("spot_sigma", "Spot sigma", 1, 0, 20, 0.1),
            ToolParameter("outline_sigma", "Outline sigma", 1, 0, 20, 0.1),
            ToolParameter("perc_int", "Intensity percentile", 100, 0, 100, 1),
        ),
    ),
    Tool(
        id="mbr_analysis",
        name="MBR analysis",
        description="Coming soon.",
        order=2,
        enabled=False,
    ),
    Tool(
        id="traction_force",
        name="Traction Force Microscopy",
        description="Traction force microscopy analysis tool.",
        order=3,
        enabled=True,
        worker_image="traction-force-worker:latest",
        parameters=(
            ToolParameter("half_window_size", "Half Window Size", 10, 4, 128, 1),
            ToolParameter("step_size", "Step Size", 10, 1, 128, 1),
            ToolParameter("mue2pix", "Micrometer to Pixel Ratio", 0.0772, 0.0001, 1.0, 0.0001),
            ToolParameter("E", "Young's Modulus (Pa)", 1200, 100, 5000, 1),
            ToolParameter("nu", "Poisson's Ratio", 0.49, 0.1, 0.9, 0.01),
            ToolParameter("alpha0", "Initial Alpha Value", 1e-15, 1e-20, 1e-10, 1e-15),
            ToolParameter("h", "Gel Height (μm)", 60, 10, 200, 1),
            ToolParameter("z", "Image Height (μm)", 60, 10, 200, 1),
            ToolParameter("d", "Dimensions of Image Stacks", 2, 1, 5, 1),
        ),
    ),
    Tool(
        id="segmentation_3d",
        name="3D Segmentation",
        description="Coming soon.",
        order=4,
        enabled=False,
    ),
)

_TOOLS_BY_ID = {tool.id: tool for tool in TOOLS}


def get_tool(tool_id: str) -> Optional[Tool]:
    return _TOOLS_BY_ID.get(tool_id)


def list_tools() -> list[Tool]:
    return sorted(TOOLS, key=lambda tool: tool.order)


def to_public_dict(tool: Tool) -> dict:
    """Shape returned to the frontend: no internal fields like the worker image."""
    return {
        "id": tool.id,
        "name": tool.name,
        "description": tool.description,
        "enabled": tool.enabled,
        "accepted_extensions": list(tool.accepted_extensions),
        "parameters": [
            {
                "name": parameter.name,
                "label": parameter.label,
                "default": parameter.default,
                "minimum": parameter.minimum,
                "maximum": parameter.maximum,
                "step": parameter.step,
            }
            for parameter in tool.parameters
        ],
    }
