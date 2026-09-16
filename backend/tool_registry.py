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
            ToolParameter("thresholdMin", "Threshold min", 0, 0, 255, 1),
            ToolParameter("thresholdMax", "Threshold max", 255, 0, 255, 1),
            ToolParameter("intensity", "Intensity", 1, 0, 10, 0.1),
            ToolParameter("percentage", "Percentage", 100, 0, 100, 1),
            ToolParameter("pixelSize", "Pixel size", 1, 0, 100, 0.1),
            ToolParameter("minSize", "Min size", 100, 0, 10000, 1),
            ToolParameter("smoothing", "Smoothing", 0, 0, 20, 1),
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
        description="Coming soon.",
        order=3,
        enabled=False,
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
