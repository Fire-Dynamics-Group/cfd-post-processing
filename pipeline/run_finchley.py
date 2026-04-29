"""Headless driver: run scenarios_object + chart pipeline against Finchley FDS data.

Untracked debugging artefact. Skips the GUI; calls the same code main.py would.
"""

import os
import sys
import json
import time
import traceback
from datetime import datetime
from pathlib import Path

# Force non-interactive matplotlib BEFORE importing anything that uses it
import matplotlib
matplotlib.use("Agg")

# Make sure we're running from the project root so relative file writes
# (e.g. the "{scenario}_etal.json" dump in scenarios_object.py) land here
PROJECT_ROOT = Path(__file__).parent.resolve()
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))


def jsonable(obj):
    """Make a thing JSON-printable. Handles numpy/pandas scalars."""
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        pass
    # numpy / pandas scalars expose .item()
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            pass
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    return str(obj)


def report_scenario(name, data):
    print(f"\n--- scenario: {name} ---")
    keys_of_interest = [
        "worst_condition",
        "tenability",
        "min_pressure",
        "door_opening_times",
        "end_time",
        "is_sprinklered",
        "venting",
    ]
    for k in keys_of_interest:
        v = data.get(k, "<MISSING>")
        print(f"  {k}: {json.dumps(jsonable(v), indent=2, default=str)}")


def main():
    # Selectable: FS2 only or both. Default: both (Rev00 Models root).
    only = os.environ.get("FINCHLEY_ONLY", "BOTH").upper()
    rev00 = (
        r"C:/Users/IanShaw/Fire Dynamics Group Dropbox (1)/"
        r"03 Modelling Data/0406 - Former Homebase Site North Finchley/Rev00 Models"
    )
    fs1 = rev00 + "/0406_Finchley_FS1_Plot80_FSA.fds_1776875134353_FDS"
    fs2 = rev00 + "/0406_Finchley_FS2_Plot84_FSA.fds_1776932523833_FDS"

    if only == "FS1":
        path_to_root_directory = fs1
    elif only == "FS2":
        path_to_root_directory = fs2
    else:
        path_to_root_directory = rev00

    print(f"path_to_root_directory: {path_to_root_directory}")

    # Output dir
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_dir_path = PROJECT_ROOT / "tmp" / "finchley_run" / ts
    new_dir_path.mkdir(parents=True, exist_ok=True)
    print(f"output dir: {new_dir_path}")

    # Step 1: scenarios_object
    print("\n=== creating scenarios_object ===")
    t0 = time.perf_counter()
    from scenarios_object import create_scenario_object
    from scen_object_helper_functions import return_scenario_names

    discovered = return_scenario_names(path_to_root_directory)
    print(f"return_scenario_names -> {discovered}")

    try:
        scenarios_object, scenario_names, FSA_scenarios, MoE_scenarios, error_list = (
            create_scenario_object(path_to_directory=path_to_root_directory)
        )
    except Exception:
        print("\n!!! create_scenario_object raised:")
        traceback.print_exc()
        return 1
    t_scen = time.perf_counter() - t0
    print(f"\ncreate_scenario_object total runtime: {t_scen:.2f}s")
    print(f"\nerror_list: {error_list if error_list else 'empty'}")
    print(f"scenario_names: {scenario_names}")
    print(f"FSA_scenarios: {FSA_scenarios}")
    print(f"MoE_scenarios: {MoE_scenarios}")

    # Dump full scenarios_object
    print("\n=== scenarios_object (per scenario) ===")
    for name in scenario_names:
        report_scenario(name, scenarios_object.get(name, {}))

    # Persist for inspection
    dump_path = new_dir_path / "scenarios_object.json"
    with open(dump_path, "w") as f:
        json.dump(jsonable(scenarios_object), f, indent=2, default=str)
    print(f"\nscenarios_object dumped: {dump_path}")

    # Step 2: charts (only if no errors)
    if error_list:
        print("\nSkipping charts because error_list is non-empty.")
        return 0

    print("\n=== running charts ===")
    from hrr_graph import run_CFD_charts

    chart_times = {}
    try:
        # The chart pipeline iterates scenarios internally. Time it as a whole.
        # But we also want per-scenario insight, so run scenarios one by one.
        for name in scenario_names:
            t1 = time.perf_counter()
            try:
                run_CFD_charts(path_to_root_directory, [name], str(new_dir_path))
            except Exception:
                print(f"\n!!! run_CFD_charts raised for scenario {name}:")
                traceback.print_exc()
            chart_times[name] = time.perf_counter() - t1
            print(f"  {name}: charts done in {chart_times[name]:.2f}s")
    except Exception:
        traceback.print_exc()

    # Inventory the PNGs
    pngs = sorted(new_dir_path.glob("*.png"))
    print(f"\nPNGs produced: {len(pngs)}")
    for p in pngs:
        print(f"  {p.name}")

    # Group by metric
    print("\n=== chart summary by metric ===")
    metrics = ["temp", "vis", "pres", "vel", "hrr", "Pressure", "Temperature", "Visibility", "Velocity"]
    for m in metrics:
        matches = [p.name for p in pngs if m.lower() in p.name.lower()]
        if matches:
            print(f"  {m}: {len(matches)}")

    # Step 3: docx render attempt (optional, best-effort)
    print("\n=== docx render attempt ===")
    try:
        attempt_docx(scenarios_object, scenario_names, new_dir_path)
    except Exception:
        print("docx render failed (non-fatal):")
        traceback.print_exc()

    print(f"\n=== TOTALS ===")
    print(f"scenarios_object runtime: {t_scen:.2f}s")
    for name, t in chart_times.items():
        print(f"  charts {name}: {t:.2f}s")
    print(f"output dir: {new_dir_path}")
    return 0


def attempt_docx(scenarios_object, scenario_names, new_dir_path):
    """Try to render the template with bare-minimum context.

    This is best-effort. If the template requires lots of values we don't have,
    just record what's missing and exit. The primary goal is the data pipeline.
    """
    template_path = PROJECT_ROOT / "Template CFD Report.docx"
    if not template_path.exists():
        print(f"  template not found at {template_path} - skipping")
        return
    try:
        from docxtpl import DocxTemplate
    except Exception as e:
        print(f"  docxtpl not importable: {e}")
        return
    doc = DocxTemplate(str(template_path))
    try:
        undeclared = doc.get_undeclared_template_variables()
    except Exception as e:
        print(f"  could not introspect template variables: {e}")
        undeclared = set()
    print(f"  template variables (count={len(undeclared)}): {sorted(undeclared)[:25]}{' ...' if len(undeclared) > 25 else ''}")

    # Build a minimal context: every unknown var defaults to empty string.
    ctx = {var: "" for var in undeclared}
    # Add a couple of plausible bindings if they exist:
    if scenario_names:
        ctx.setdefault("scenarios", scenario_names)
        ctx.setdefault("FSA_scenarios", [n for n in scenario_names if "FSA" in n])
    try:
        doc.render(ctx)
        out = new_dir_path / "output.docx"
        doc.save(str(out))
        print(f"  docx rendered: {out}")
    except Exception:
        print("  doc.render raised:")
        traceback.print_exc()


if __name__ == "__main__":
    sys.exit(main())
