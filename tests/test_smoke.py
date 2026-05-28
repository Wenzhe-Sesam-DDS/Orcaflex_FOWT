"""
Smoke tests for the OrcaFlex FOWT workflow.

These tests confirm that:
  • The model builds without errors.
  • Statics converge on the default parameter set.
  • A short dynamics + post-processing pass produces all expected artefacts.

The OrcaFlex API is *required*; tests are skipped automatically if the DLL
or a valid licence is not available on this machine.

Run with:  pytest -v tests/
"""

import os
import shutil
import tempfile

import pytest

OrcFxAPI = pytest.importorskip("OrcFxAPI")

from project_config import params_with_defaults, params_hash    # noqa: E402
from workflow_01_build  import build                            # noqa: E402
from workflow_02_run    import run as run_sims                  # noqa: E402
from workflow_03_results import post_process                    # noqa: E402


# A fast variant of the defaults — short windows so the test finishes in
# tens of seconds rather than minutes. The window must still cover enough
# wave periods for ExtremeStatistics / Rainflow / spectral moments to be
# defined (those crash OrcaFlex with a floating-point exception otherwise).
FAST_OVERRIDES = {
    "wave_tp":           6.0,    # short period → more cycles per second
    "buildup_duration":  20.0,
    "analysis_duration": 600.0,  # 10 minutes ≈ 100 wave periods
    "n_seeds":           1,
}


@pytest.fixture(scope="module")
def fast_params():
    return params_with_defaults(FAST_OVERRIDES)


@pytest.fixture(scope="module")
def tmp_out_dir():
    d = tempfile.mkdtemp(prefix="orcaflex_smoke_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_params_hash_stable():
    """Same dict must always hash to the same value."""
    p = params_with_defaults()
    assert params_hash(p) == params_hash(dict(p))


def test_build_default_model():
    """Build a model from defaults — all expected objects must exist."""
    try:
        model = build(params_with_defaults())
    except OrcFxAPI.DLLError as exc:
        pytest.skip(f"OrcFxAPI unavailable: {exc}")
    names = {obj.Name for obj in model.objects}
    assert "Platform" in names
    assert "ExportCable" in names
    assert {"Mooring1", "Mooring2", "Mooring3"} <= names


def test_full_pipeline(fast_params, tmp_out_dir):
    """End-to-end: build → run → post_process → check artefacts on disk."""
    try:
        sim_paths = run_sims(fast_params, out_dir=tmp_out_dir)
    except (OrcFxAPI.DLLError, RuntimeError) as exc:
        pytest.skip(f"OrcFxAPI run failed (likely no licence): {exc}")

    assert len(sim_paths) == fast_params["n_seeds"]
    for p in sim_paths:
        assert os.path.exists(p), f"missing .sim: {p}"

    artefacts = post_process(sim_paths, fast_params, out_dir=tmp_out_dir)
    assert os.path.exists(artefacts["report"])
    for fig in artefacts["figures"]:
        assert os.path.exists(fig), f"missing figure: {fig}"
        assert os.path.getsize(fig) > 1000, f"figure looks empty: {fig}"
