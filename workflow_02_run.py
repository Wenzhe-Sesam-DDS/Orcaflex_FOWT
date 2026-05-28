"""
OrcaFlex Workflow — Step 2: Run Simulation
==========================================
Loads or accepts a built model, executes the full analysis sequence, and
saves the completed simulation to a `.sim` file for post-processing.

Analysis sequence
  CalculateStatics()  — finds static equilibrium (catenary shape, platform offset)
  RunSimulation()     — time-domain dynamics for all stages defined in General

Multi-seed support
  Pass `n_seeds > 1` in `params` to run several independent random-phase
  simulations (seed i uses WaveSeed = base_seed + i). Each `.sim` is written
  to a separate file, and the list of paths is returned for post-processing.

Public API
  run(params, out_dir, model=None) -> list[str]
      Run statics + dynamics for every seed and return the saved .sim paths.

Standalone CLI: loads testModel.dat (built by workflow_01_build.py),
  runs a single simulation, and saves testModel.sim next to this script.
"""

import os
import sys

import OrcFxAPI

from project_config import params_with_defaults
from workflow_01_build import build

HERE = os.path.dirname(os.path.abspath(__file__))


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════
def run(params: dict,
        out_dir: str,
        model: OrcFxAPI.Model | None = None) -> list[str]:
    """Run statics + dynamics for every requested seed.

    Parameters
    ----------
    params : dict      — full params dict (see project_config.GUI_DEFAULTS)
    out_dir : str      — directory to write `.sim` files into
    model  : Model     — pre-built model. If None, build() is called once.

    Returns
    -------
    List of `.sim` paths, in seed order.
    """
    p          = params_with_defaults(params)
    n_seeds    = max(1, int(p["n_seeds"]))
    base_seed  = int(p["wave_seed"])

    os.makedirs(out_dir, exist_ok=True)

    if model is None:
        model = build(p)

    sim_paths: list[str] = []
    for i in range(n_seeds):
        seed = base_seed + i
        model.Reset()                          # clear any prior dynamic results
        model.environment.WaveSeed = seed

        try:
            model.CalculateStatics()
        except OrcFxAPI.DLLError as e:
            raise RuntimeError(f"Statics failed (seed {seed}): {e}") from e

        try:
            model.RunSimulation()
        except OrcFxAPI.DLLError as e:
            raise RuntimeError(f"Dynamics failed (seed {seed}): {e}") from e

        if n_seeds == 1:
            sim_name = "testModel.sim"
        else:
            sim_name = f"testModel_seed{i:02d}.sim"
        sim_path = os.path.join(out_dir, sim_name)
        model.SaveSimulation(sim_path)
        sim_paths.append(sim_path)
        print(f"  seed {seed} ({i+1}/{n_seeds}) → {sim_name}")

    return sim_paths


# ══════════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
def main():
    dat_path = os.path.join(HERE, "testModel.dat")
    if not os.path.exists(dat_path):
        print(
            f"\nERROR — model data file not found: {dat_path}\n"
            f"        Run workflow_01_build.py first to build the model.",
            file=sys.stderr,
        )
        sys.exit(1)

    model = OrcFxAPI.Model(dat_path)
    print(f"Model loaded.             State: {model.state.name}")
    print(f"  Analysis duration : {sum(model.general.StageDuration):.0f} s total  "
          f"({model.general.StageDuration[0]:.0f} s build-up + "
          f"{model.general.StageDuration[1]:.0f} s analysis)")
    print(f"  Sea state         : Hs = {model.environment.WaveHs:.2f} m, "
          f"Tp = {model.environment.WaveTp:.2f} s")

    params = params_with_defaults()
    try:
        sim_paths = run(params, out_dir=HERE, model=model)
    except RuntimeError as exc:
        print(f"\nERROR — {exc}", file=sys.stderr)
        sys.exit(1)

    # Static sanity print using the final solved state
    print("\n  Static mooring tensions (last run):")
    print(f"  {'Line':<12}  {'EndA (kN)':>12}  {'EndB (kN)':>12}")
    for obj in model.objects:
        if obj.Name.startswith("Mooring"):
            Te_A = obj.StaticResult("Effective tension", OrcFxAPI.oeEndA)
            Te_B = obj.StaticResult("Effective tension", OrcFxAPI.oeEndB)
            print(f"  {obj.Name:<12}  {Te_A:12.1f}  {Te_B:12.1f}")

    print(f"\nSimulation(s) saved:")
    for path in sim_paths:
        print(f"  {path}")
    print("Next step: run workflow_03_results.py")


if __name__ == "__main__":
    main()
