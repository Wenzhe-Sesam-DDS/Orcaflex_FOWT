# OrcaFlex FOWT Analysis

A reusable Python + Streamlit pipeline for floating offshore wind turbine
(FOWT) analyses using the Orcina OrcaFlex API. Models a semi-submersible
platform with a 3-leg catenary mooring system and a lazy-wave dynamic
export cable, runs irregular-sea time-domain simulations across one or more
random seeds, and post-processes motions, mooring tensions, cable integrity
and seed-aggregated extreme statistics.

> **License requirement.** OrcaFlex (Orcina Ltd.) and a valid Python API
> licence are required. The `OrcFxAPI` package must be importable in your
> environment.

---

## Quick start

```powershell
# Create + activate the project venv (Python 3.10+ recommended)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install streamlit numpy matplotlib pytest
# OrcFxAPI ships with your OrcaFlex install — point pip at its wheel or
# add the OrcaFlex Python directory to PYTHONPATH.

# Launch the GUI
streamlit run app.py
```

Open the URL Streamlit prints, set parameters in the sidebar, and click
**▶ Run Analysis**.

---

## Project layout

| File / dir | Purpose |
|---|---|
| `app.py` | Streamlit GUI; calls each workflow function in-process |
| `project_config.py` | Defaults + helpers (`params_with_defaults`, `params_hash`, `MOORING_HEADINGS`) |
| `workflow_01_build.py` | `build(params) -> Model` — model construction |
| `workflow_02_run.py`   | `run(params, out_dir, model=None) -> list[sim_path]` — statics + dynamics, supports multi-seed |
| `workflow_03_results.py` | `post_process(sim_paths, params, out_dir) -> {report, figures}` — report + figures, seed-aggregated extremes |
| `tests/test_smoke.py` | `pytest` end-to-end smoke test (auto-skips without OrcFxAPI) |
| `runs/<hash>/` | Cached outputs per unique parameter set |

Each workflow script also exposes a standalone CLI entry point, so you can
run them sequentially from a terminal without the GUI.

---

## Multi-seed extreme statistics

Set **Number of Seeds = N** in the sidebar (or `n_seeds` in the params
dict). The runner executes N independent simulations using
`WaveSeed = base_seed + i`, then `post_process` fits a Rayleigh tail per
seed and reports the **mean ± std + worst** of each MPM / risk-factor
estimate. Plots are drawn from seed 0.

For stable extreme-value estimates: **N ≥ 3** is recommended; **N ≥ 5**
for design-grade ULS reports.

---

## Output caching

`app.py` hashes the full params dict and writes all artefacts to
`runs/<hash>/`. Re-running with the same parameters reuses the cached
artefacts instead of recomputing. To force a re-run, delete the
corresponding `runs/<hash>/` directory or change any parameter.

---

## Testing

```powershell
.\.venv\Scripts\Activate.ps1
pytest -v tests/
```

The smoke test builds a model, runs a short 10-minute simulation, and
asserts every expected artefact exists. It is skipped automatically if
`OrcFxAPI` cannot be imported.

> The repo's `pytest.ini` disables pytest's `faulthandler` plugin —
> OrcFxAPI's internal solver raises and *catches* x87 FPU
> invalid-operation signals during heavy numeric work, and
> `faulthandler` otherwise prints them as `Windows fatal exception:
> code 0xc0000090` and aborts the session.

---

## Known modelling simplifications

* The Platform uses the OrcaFlex **default VesselType** (no RAOs, no
  diffraction, no wind / current drag). Sway / Roll / Yaw read as zero.
  For a representative FOWT, import a project-specific VesselType built
  from WAMIT / AQWA output, then assign it to the Platform in `build()`.
* Wind is modelled as constant; no rotor-thrust time series.
* Current is a single-depth profile (`RefCurrentSpeed`); add depth rows
  via `SetDataRowCount` for a sheared profile.
* Mooring chain bending / torsion stiffness is zero (standard chain
  assumption); replace with a composite chain–wire–chain line type for
  detailed studies.

---

## License

See `LICENSE`.
