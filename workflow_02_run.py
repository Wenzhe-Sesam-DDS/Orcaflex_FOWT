"""
OrcaFlex Workflow — Step 2: Run Simulation
==========================================
Loads testModel.dat (built in Step 1), executes the full analysis sequence,
and saves the completed simulation to testModel.sim for post-processing.

Analysis sequence
  CalculateStatics()  — finds static equilibrium (catenary shape, platform offset)
  RunSimulation()     — time-domain dynamics for all stages defined in General

Model state machine
  Reset state  ──CalculateStatics()──►  Static state
  Static state ──RunSimulation()──────►  Simulation complete
  Any state    ──Reset()──────────────►  Reset state  (clears dynamic results)

Parametric studies
  To run multiple load cases without rebuilding the model each time:
    for hs in wave_heights:
        model.environment.WaveHs = hs           # change a parameter
        model.Reset()                           # return to reset state
        model.RunSimulation()                   # re-run dynamics
        model.SaveSimulation(f"case_Hs{hs}.sim")

Requires: workflow_01_build.py must have been run first (testModel.dat).
Next step: workflow_03_results.py
"""

import os
import sys
import OrcFxAPI

HERE     = os.path.dirname(os.path.abspath(__file__))
DAT_PATH = os.path.join(HERE, "testModel.dat")
SIM_PATH = os.path.join(HERE, "testModel.sim")

# ══════════════════════════════════════════════════════════════════════════════
# 1. LOAD MODEL
# ══════════════════════════════════════════════════════════════════════════════
# Constructor accepts .dat (binary), .yml, or .json OrcaFlex data formats.
model = OrcFxAPI.Model(DAT_PATH)
print(f"Model loaded.             State: {model.state.name}")
print(f"  Analysis duration : {sum(model.general.StageDuration):.0f} s total  "
      f"({model.general.StageDuration[0]:.0f} s build-up + "
      f"{model.general.StageDuration[1]:.0f} s analysis)")
print(f"  Sea state         : Hs = {model.environment.WaveHs:.2f} m, "
      f"Tp = {model.environment.WaveTp:.2f} s")

# ══════════════════════════════════════════════════════════════════════════════
# 2. STATIC EQUILIBRIUM
# ══════════════════════════════════════════════════════════════════════════════
# Solves for the equilibrium configuration under mean wind / current / gravity.
# After this step, StaticResult() and RangeGraph() (without a period) are valid.
try:
    model.CalculateStatics()
except OrcFxAPI.DLLError as e:
    print(f"\nERROR — statics did not converge: {e}", file=sys.stderr)
    sys.exit(1)
print(f"\nAfter CalculateStatics.   State: {model.state.name}")

# --- Static sanity checks ---
platform = model["Platform"]

# All mooring lines — check static tension at fairlead (End A) and anchor (End B)
print("\n  Static mooring tensions:")
print(f"  {'Line':<12}  {'EndA (kN)':>12}  {'EndB (kN)':>12}")
for obj in model.objects:
    if obj.Name.startswith("Mooring"):
        Te_A = obj.StaticResult("Effective tension", OrcFxAPI.oeEndA)
        Te_B = obj.StaticResult("Effective tension", OrcFxAPI.oeEndB)
        print(f"  {obj.Name:<12}  {Te_A:12.1f}  {Te_B:12.1f}")

# Dynamic cable — check static tension and minimum bend radius at ends
cable = model["ExportCable"]
Te_cable_A = cable.StaticResult("Effective tension", OrcFxAPI.oeEndA)
Te_cable_B = cable.StaticResult("Effective tension", OrcFxAPI.oeEndB)
print(f"\n  Export cable static tension:  End A = {Te_cable_A:.1f} kN, "
      f"End B = {Te_cable_B:.1f} kN")

# Static platform offset (X, Y displacement from origin)
X_static = platform.StaticResult("X")
Y_static = platform.StaticResult("Y")
print(f"\n  Platform static offset:  X = {X_static:.2f} m,  Y = {Y_static:.2f} m")

# ══════════════════════════════════════════════════════════════════════════════
# 3. DYNAMIC TIME-DOMAIN SIMULATION
# ══════════════════════════════════════════════════════════════════════════════
# Runs all stages defined in General.StageDuration.
# For Marine Ops weather-window studies, loop over multiple wave seeds here
# and aggregate results before saving the final .sim.
try:
    model.RunSimulation()
except OrcFxAPI.DLLError as e:
    print(f"\nERROR — dynamic simulation failed: {e}", file=sys.stderr)
    sys.exit(1)
print(f"\nAfter RunSimulation.      State: {model.state.name}")

# ══════════════════════════════════════════════════════════════════════════════
# 4. SAVE SIMULATION RESULTS
# ══════════════════════════════════════════════════════════════════════════════
# The .sim file stores both model data and all calculated time histories.
# workflow_03_results.py loads this file for post-processing.
model.SaveSimulation(SIM_PATH)
print(f"\nSimulation saved: {SIM_PATH}")
print("Next step: run workflow_03_results.py")
