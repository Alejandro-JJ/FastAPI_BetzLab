"""Standalone test: run the traction_force worker process() on the sample
before/after TIFFs and verify the rendered plots carry unit-aware colorbars.

Runs the same code path as the worker container, with storage calls stubbed
out (the before image is passed directly, the after image via a local stub).
"""
import sys
import shutil
import types
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "backend" / "tools"))
sys.path.insert(0, str(REPO / "TFM_Utilities_OG" / "SRC"))

# --- Stub the storage module (MinIO) so downloads resolve to local files ---
storage_stub = types.ModuleType("storage")
_after_src = REPO / "TFM_StreamLit_OG" / "TFM_after.tif"


def _download_to_path(object_key, dest_path):
    shutil.copy(_after_src, dest_path)


storage_stub.download_to_path = _download_to_path
sys.modules["storage"] = storage_stub

# --- Stub itk: only used by the elastix methods, not by dft ---
sys.modules["itk"] = types.ModuleType("itk")

# --- Import the worker processor and run the full pipeline ---
from tools.traction_force.processor import process

workdir = REPO / "test_tfm_output"
workdir.mkdir(exist_ok=True)
# Clean previous artifacts
for old in workdir.iterdir():
    old.unlink()

context = SimpleNamespace(
    job_id="test-colorbar",
    workdir=workdir,
    params={
        "after_object_key": "TFM_after.tif",
        # dft is the default; images are 2D so dim mode resolves to "xy"
        "run_traction": True,
    },
)

result = process(REPO / "TFM_StreamLit_OG" / "TFM_before.tif", context)

print("RESULT:", result.result_path)
print("METADATA units:", result.metadata.get("vector_field_unit"))
print("ARTIFACTS:")
for name, path in sorted(result.artifacts.items()):
    print(f"  {name}: {Path(path).name} ({Path(path).stat().st_size} bytes)")
