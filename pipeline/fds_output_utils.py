import os
import re
import math


# ---- FDS namelist parsing -------------------------------------------------

# Match a single namelist record: &KEY ... / (records may span multiple
# physical lines). DOTALL so . matches newlines inside a record.
_NAMELIST_RE = re.compile(r"&([A-Z]+)\s+(.*?)/", re.DOTALL)

# Match a key=value pair where value can be:
#   - quoted string:   'foo' or "foo"
#   - logical:         .TRUE. / .FALSE. / .T. / .F.
#   - number(s):       single or comma-separated list of numbers
#   - identifier list: 'a','b','c' (single-quoted comma-separated)
# We collect everything up to the next " key=" boundary or end of record.
# The number-list branch must not stop at internal commas (e.g.
# "XYZ=1.0,2.0,3.0") so we consume up to the next ", KEY=" boundary.
_PAIR_RE = re.compile(
    r"([A-Z_][A-Z0-9_]*)\s*=\s*("
    r"(?:'[^']*'(?:\s*,\s*'[^']*')*)"        # quoted string list
    r"|(?:\"[^\"]*\")"                       # double-quoted
    r"|(?:\.(?:TRUE|FALSE|T|F)\.)"           # logical
    r"|(?:[+\-0-9.eE][^=]*?)"                # number / number list (lazy)
    r")"
    r"(?=\s*,\s*[A-Z_][A-Z0-9_]*\s*=|\s*$)",
    re.IGNORECASE | re.DOTALL,
)


def _parse_logical(text):
    t = text.strip().upper()
    return t in (".TRUE.", ".T.")


def _parse_string_list(text):
    """'a','b','c' -> ['a', 'b', 'c']; 'a' -> ['a']."""
    return re.findall(r"'([^']*)'", text)


def _parse_floats(text):
    """Comma-separated numbers -> list[float]. Tolerates trailing junk."""
    out = []
    for tok in text.split(","):
        tok = tok.strip()
        if not tok:
            continue
        m = re.match(r"[+\-]?(?:[0-9]*[.])?[0-9]+(?:[eE][+\-]?[0-9]+)?", tok)
        if m:
            try:
                out.append(float(m.group(0)))
            except ValueError:
                pass
    return out


def _parse_namelists(text):
    """Yield dicts {kind, raw, params} for every &KIND ... / record."""
    records = []
    for m in _NAMELIST_RE.finditer(text):
        kind = m.group(1).upper()
        body = m.group(2)
        params = {}
        for pm in _PAIR_RE.finditer(body):
            params[pm.group(1).upper()] = pm.group(2).strip()
        records.append({"kind": kind, "raw": m.group(0), "params": params})
    return records


# ---- Side classification --------------------------------------------------

# Order matters: stair must be checked before lobby (since some IDs contain
# both "stair" and "lobby"); apartment cues are last in the apt set.
_APT_TOKENS = ("apt", "apartment", "fire floor", "fire_floor")
_STAIR_TOKENS = ("stair",)
_LOBBY_TOKENS = ("lobby",)  # treated as apartment-side per spec


def _classify_by_id(*ids):
    """Return 'apartment'|'stair'|None based on substring match across IDs."""
    blob = " ".join(i for i in ids if i).lower()
    if any(t in blob for t in _STAIR_TOKENS):
        return "stair"
    if any(t in blob for t in _APT_TOKENS):
        return "apartment"
    if any(t in blob for t in _LOBBY_TOKENS):
        return "apartment"
    return None


# ---- Public API -----------------------------------------------------------

def find_door_opening_times(path_to_file):
    """Parse an FDS file for door-open / door-close events.

    Recognises three patterns:
      1. Modern: &DEVC QUANTITY='TIME' -> &CTRL (optionally with inverter
         INITIAL_STATE=.TRUE.) -> &OBST/&HOLE/&VENT with CTRL_ID.
      2. Legacy literal: &CTRL ID='Apt_Door_*' / 'Stair_Door_*' with SETPOINT.
      3. Legacy RAMP: a line containing '*Door_RAMP' or '*Hole_RAMP' with
         T= time and F= polarity (preserved from the original implementation).

    Returns:
      {'opening_apartment': float, 'closing_apartment': float|None,
       'opening_stair': float, 'closing_stair': float|None}
    """
    with open(path_to_file, "r") as f:
        text = f.read()

    records = _parse_namelists(text)

    # Build indices
    devcs_by_id = {}
    ctrls_by_id = {}
    geometries = []
    for rec in records:
        params = rec["params"]
        ident = _strip_quotes(params.get("ID", ""))
        if rec["kind"] == "DEVC" and ident:
            devcs_by_id[ident] = {
                "id": ident,
                "quantity": _strip_quotes(params.get("QUANTITY", "")).upper(),
                "setpoint": (_parse_floats(params["SETPOINT"])[0]
                             if "SETPOINT" in params else None),
                "initial_state": _parse_logical(
                    params.get("INITIAL_STATE", ".FALSE.")),
                "xyz": _parse_floats(params.get("XYZ", "")),
            }
        elif rec["kind"] == "CTRL" and ident:
            input_ids = _parse_string_list(params.get("INPUT_ID", ""))
            ctrls_by_id[ident] = {
                "id": ident,
                "function_type": _strip_quotes(
                    params.get("FUNCTION_TYPE", "ALL")).upper(),
                "input_ids": input_ids,
                "initial_state": _parse_logical(
                    params.get("INITIAL_STATE", ".FALSE.")),
                "delay": (_parse_floats(params.get("DELAY", "0"))[0]
                          if params.get("DELAY") else 0.0),
                "setpoint": (_parse_floats(params["SETPOINT"])[0]
                             if "SETPOINT" in params else None),
                "raw": rec["raw"],
            }
        elif rec["kind"] in ("OBST", "HOLE", "VENT"):
            ctrl_id = _strip_quotes(params.get("CTRL_ID", "")) or None
            devc_id = _strip_quotes(params.get("DEVC_ID", "")) or None
            if not (ctrl_id or devc_id):
                continue
            xb = _parse_floats(params.get("XB", ""))
            geometries.append({
                "kind": rec["kind"],
                "id": ident,
                "ctrl_id": ctrl_id,
                "devc_id": devc_id,
                "xb": xb,
            })

    events = []  # list of (time: float, action: 'open'|'close', side: str|None)

    # Pattern 1: chain-resolved geometry events
    for geom in geometries:
        time_val, final_state_true = _resolve_chain(
            geom, ctrls_by_id, devcs_by_id)
        if time_val is None:
            continue
        action = _geometry_action(geom["kind"], final_state_true)
        side = _classify_geometry(geom, ctrls_by_id, devcs_by_id)
        events.append((time_val, action, side))

    # Pattern 2: legacy literal CTRL ID 'Apt_Door' / 'Stair_Door' with SETPOINT
    for ctrl in ctrls_by_id.values():
        cid = ctrl["id"]
        if ctrl["setpoint"] is None:
            continue
        if "Apt_Door" in cid or "Stair_Door" in cid:
            side = _classify_by_id(cid) or (
                "stair" if "stair" in cid.lower() else "apartment")
            # The legacy heuristic: TRUE in raw line -> open, else close
            action = "open" if ".TRUE." in ctrl["raw"].upper() else "close"
            events.append((ctrl["setpoint"], action, side))

    # Pattern 3: legacy RAMP heuristic on raw lines
    for line in text.splitlines():
        events.extend(_legacy_ramp_events(line))

    # Aggregate
    opening_apt = [t for (t, a, s) in events if a == "open" and s == "apartment"]
    closing_apt = [t for (t, a, s) in events if a == "close" and s == "apartment"]
    opening_stair = [t for (t, a, s) in events if a == "open" and s == "stair"]
    closing_stair = [t for (t, a, s) in events if a == "close" and s == "stair"]

    open_apt_v = min(opening_apt) if opening_apt else 0
    close_apt_v = max(closing_apt) if closing_apt else None
    open_stair_v = min(opening_stair) if opening_stair else 0
    close_stair_v = max(closing_stair) if closing_stair else None

    # Legacy sanity checks: closing must come after opening; identical
    # opening/closing means no real close.
    if close_apt_v is not None and close_apt_v < open_apt_v:
        close_apt_v = None
    if close_stair_v is not None and close_stair_v == open_stair_v:
        close_stair_v = None

    return {
        "opening_apartment": open_apt_v,
        "closing_apartment": close_apt_v,
        "opening_stair": open_stair_v,
        "closing_stair": close_stair_v,
    }


def find_door_opening_times_with_close_defaults(path_to_file):
    """Same as ``find_door_opening_times``, but replaces ``None`` close
    events with the legacy 80s default.

    Use this when downstream code can't handle ``None`` (tenability
    arithmetic in ``scenarios_object``, the "+120s after Door Closes"
    chart marker in ``hrr_graph``). The base function preserves the
    ``None`` signal for callers that need to know the FDS file lacks a
    close event.
    """
    door_times = find_door_opening_times(path_to_file)
    if door_times.get("closing_apartment") is None:
        door_times["closing_apartment"] = 80
    if door_times.get("closing_stair") is None:
        door_times["closing_stair"] = 80
    return door_times


# ---- Helpers --------------------------------------------------------------

def _strip_quotes(s):
    if not s:
        return s
    s = s.strip()
    if (s.startswith("'") and s.endswith("'")) or (
        s.startswith('"') and s.endswith('"')):
        return s[1:-1]
    return s


def _resolve_chain(geom, ctrls, devcs):
    """Walk geometry -> CTRL -> DEVC(s) and return (time, final_state_true).

    final_state_true is True if the controller drives the geometry's state to
    TRUE at trigger time, False otherwise.
    """
    if geom["devc_id"] and geom["devc_id"] in devcs:
        d = devcs[geom["devc_id"]]
        if d["quantity"] == "TIME" and d["setpoint"] is not None:
            # Direct DEVC drives geometry. Final state = NOT(devc.initial_state).
            return d["setpoint"], not d["initial_state"]
    if not geom["ctrl_id"] or geom["ctrl_id"] not in ctrls:
        return None, None
    return _resolve_ctrl(ctrls[geom["ctrl_id"]], ctrls, devcs)


def _resolve_ctrl(ctrl, ctrls, devcs, _seen=None):
    """Return (time, final_state_true) for a CTRL by walking its inputs."""
    if _seen is None:
        _seen = set()
    if ctrl["id"] in _seen:
        return None, None
    _seen.add(ctrl["id"])

    times = []
    for inp in ctrl["input_ids"]:
        if inp in devcs:
            d = devcs[inp]
            if d["quantity"] == "TIME" and d["setpoint"] is not None:
                times.append(d["setpoint"])
        elif inp in ctrls:
            t, _ = _resolve_ctrl(ctrls[inp], ctrls, devcs, _seen)
            if t is not None:
                times.append(t)
    if not times:
        return None, None

    if ctrl["function_type"] == "ANY":
        eff = min(times)
    else:  # default ALL (and any other type we don't model in detail)
        eff = max(times)
    eff += ctrl["delay"] or 0.0
    # The "inverter" trick: a single-input CTRL with INITIAL_STATE=.TRUE.
    # ends up FALSE at trigger time. Generalise: final state = NOT(initial).
    return eff, not ctrl["initial_state"]


def _geometry_action(kind, final_state_true):
    """OBST/HOLE/VENT polarity rules.

    OBST: state TRUE = present (door closed). TRUE -> FALSE = OPEN.
    HOLE: state TRUE = void exists (door open). FALSE -> TRUE = OPEN.
    VENT: state TRUE = active. Treat like HOLE for door-opening semantics.
    """
    if kind == "OBST":
        return "open" if not final_state_true else "close"
    return "open" if final_state_true else "close"


def _classify_geometry(geom, ctrls, devcs):
    """apt / stair / None classification for an event."""
    # 1. Geometry ID, CTRL ID, then upstream DEVC IDs
    side = _classify_by_id(geom["id"])
    if side:
        return side
    if geom["ctrl_id"]:
        side = _classify_by_id(geom["ctrl_id"])
        if side:
            return side
        # walk upstream DEVCs for ID hints
        ctrl = ctrls.get(geom["ctrl_id"])
        if ctrl:
            for inp in ctrl["input_ids"]:
                side = _classify_by_id(inp)
                if side:
                    return side
    if geom["devc_id"]:
        side = _classify_by_id(geom["devc_id"])
        if side:
            return side

    # 2. Spatial fallback: nearest known cluster DEVC by centroid
    if not geom["xb"] or len(geom["xb"]) < 6:
        return None
    cx = (geom["xb"][0] + geom["xb"][1]) / 2.0
    cy = (geom["xb"][2] + geom["xb"][3]) / 2.0
    cz = (geom["xb"][4] + geom["xb"][5]) / 2.0

    best = (None, math.inf)  # (side, distance)
    for d in devcs.values():
        side = _devc_cluster_side(d["id"])
        if side is None or len(d["xyz"]) < 3:
            continue
        dx = d["xyz"][0] - cx
        dy = d["xyz"][1] - cy
        dz = d["xyz"][2] - cz
        dist = (dx * dx + dy * dy + dz * dz) ** 0.5
        if dist < best[1]:
            best = (side, dist)
    return best[0]


def _devc_cluster_side(devc_id):
    """Map known DEVC-name clusters to apartment/stair side."""
    if not devc_id:
        return None
    lid = devc_id.lower()
    if lid.startswith("stair") or "stair_" in lid:
        return "stair"
    if (lid.startswith("cc_") or lid.startswith("corridor_") or
            lid.startswith("lobby_") or lid.startswith("Lobby_".lower())):
        return "apartment"
    return None


# ---- Legacy RAMP heuristics (preserved verbatim semantics) ----------------

_RAMP_FLOAT = r"[+-]?([0-9]*[.])?[0-9]+"


def _legacy_ramp_events(line):
    """Yield events for the original RAMP-detection heuristic.

    Reproduces the original branch in find_door_opening_times that walked the
    file line-by-line looking for "T=" plus a ramp-name suffix.
    """
    out = []
    if "inlet" in line.lower():
        return out
    if "T=" not in line:
        return out
    lower = line.lower()
    if not (
        "door_ramp'," in lower
        or "hole_ramp'," in lower
        or "apt_ramp" in lower
    ):
        return out
    parts = line.split(",")
    if len(parts) < 2:
        return out
    nums = re.findall(_RAMP_FLOAT, parts[1])
    if not nums:
        return out
    # re.findall returns the captured groups; we need the full numeric token.
    m = re.search(_RAMP_FLOAT, parts[1])
    door_time = float(m.group(0)) if m else None
    if door_time is None:
        return out
    last = parts[-1]
    has_minus = "-" in last
    is_hole = "hole" in lower

    def emit(side):
        # Polarity rules from the original implementation.
        if has_minus:
            action = "close" if is_hole else "open"
        else:
            action = "open" if is_hole else "close"
        out.append((door_time, action, side))

    if "apartment" in lower or "apt" in lower:
        emit("apartment")
    if "stair" in lower:
        emit("stair")
    return out


if __name__ == '__main__':
    path_to_file = (
        r'C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects'
        r' CFD\31. Camp Hill Gardens Corridor\FS4_FSA\FS4_FSA\FS4_FSA.fds'
    )
    door_times = find_door_opening_times(path_to_file)
    print(door_times)
