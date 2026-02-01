from __future__ import annotations

# --- bootstrap sys.path so "src/" is importable even in Blender --python mode ---
import sys
from pathlib import Path

THIS = Path(__file__).resolve()
ROOT = THIS.parents[1]          # D:\AudioV
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
# ------------------------------------------------------------------------------

import argparse
from pathlib import Path as _Path

import bpy

from audiov.midi_sheet import NoteEvent, parse_midi_notes, normalize_notes


def _argv_after_double_dash(argv: list[str]) -> list[str]:
    if "--" in argv:
        return argv[argv.index("--") + 1 :]
    return []


def _ensure_collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def _remove_object(o: bpy.types.Object) -> None:
    for c in list(o.users_collection):
        c.objects.unlink(o)
    if o.users == 0:
        bpy.data.objects.remove(o)


def _clear_collection(col: bpy.types.Collection) -> None:
    for o in list(col.objects):
        col.objects.unlink(o)
        if o.users == 0:
            bpy.data.objects.remove(o)


def _get_or_create_material(name: str) -> bpy.types.Material:
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True  # ok for Blender 5; we'll modernize later
        nt = mat.node_tree
        if nt:
            bsdf = nt.nodes.get("Principled BSDF")
            if bsdf and "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = 1.0
    return mat


def build_piano_roll(
    notes: list[NoteEvent],
    *,
    pitch_min: int,
    collection_name: str = "MIDI_SHEET",
    time_scale: float = 1.0,
    pitch_scale: float = 0.1,
    bar_height: float = 0.06,
    velocity_scale: float = 1.0,
) -> bpy.types.Collection:
    col = _ensure_collection(collection_name)
    _clear_collection(col)

    if not notes:
        print("[AudioV] No notes found.")
        return col

    mat = _get_or_create_material("MAT_MIDI_NOTE")

    import bmesh

    for i, n in enumerate(notes):
        start = n.start_s * time_scale
        dur = max((n.end_s - n.start_s) * time_scale, 1e-6)
        y = (n.pitch - pitch_min) * pitch_scale

        mesh = bpy.data.meshes.new(f"note_{i:05d}_mesh")
        obj = bpy.data.objects.new(f"note_{i:05d}", mesh)
        col.objects.link(obj)

        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(mesh)
        bm.free()

        vfac = max(n.velocity / 127.0, 0.05) * velocity_scale
        obj.scale.x = dur * 0.5
        obj.scale.y = 0.02
        obj.scale.z = bar_height * (0.5 + vfac)

        obj.location.x = start + dur * 0.5
        obj.location.y = y
        obj.location.z = obj.scale.z

        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)

    print(f"[AudioV] Built piano roll: {len(notes)} notes | pitch_min {pitch_min}")
    return col


def _simplify_note_stream(notes: list[NoteEvent]) -> list[NoteEvent]:
    # one point per note start (sorted)
    return sorted(notes, key=lambda n: (n.start_s, n.pitch))


def build_path_curve_from_notes(
    notes: list[NoteEvent],
    *,
    pitch_min: int,
    collection_name: str = "MIDI_PATH",
    time_scale: float = 1.0,
    pitch_scale: float = 0.1,
    z: float = 0.02,
    curve_name: str = "MIDI_PATH",
) -> bpy.types.Object:
    col = _ensure_collection(collection_name)
    _clear_collection(col)

    old_obj = bpy.data.objects.get(curve_name)
    if old_obj:
        _remove_object(old_obj)
    old_curve = bpy.data.curves.get(curve_name)
    if old_curve:
        bpy.data.curves.remove(old_curve)

    targets = _simplify_note_stream(notes)

    crv = bpy.data.curves.new(curve_name, type="CURVE")
    crv.dimensions = "3D"
    crv.resolution_u = 24

    # IMPORTANT: Blender 5.0 does not accept fill_mode="NONE".
    # For a path curve, we keep it purely a curve with no bevel/extrude.
    crv.bevel_depth = 0.0
    crv.extrude = 0.0

    spl = crv.splines.new("POLY")
    if not targets:
        spl.points.add(1)
        spl.points[0].co = (0.0, 0.0, z, 1.0)
        spl.points[1].co = (1.0, 0.0, z, 1.0)
    else:
        spl.points.add(len(targets) - 1)
        for i, n in enumerate(targets):
            x = n.start_s * time_scale
            y = (n.pitch - pitch_min) * pitch_scale
            spl.points[i].co = (x, y, z, 1.0)

    obj = bpy.data.objects.new(curve_name, crv)
    col.objects.link(obj)

    print(f"[AudioV] Built path curve: {len(targets)} pts -> {curve_name}")
    return obj


def ensure_drop_rig(
    path_obj: bpy.types.Object,
    *,
    collection_name: str = "MIDI_DROP",
    drop_name: str = "DROP",
) -> bpy.types.Object:
    col = _ensure_collection(collection_name)

    drop = bpy.data.objects.get(drop_name)
    if drop is None:
        drop = bpy.data.objects.new(drop_name, None)
        drop.empty_display_type = "SPHERE"
        drop.empty_display_size = 0.12
        col.objects.link(drop)

    c = drop.constraints.get("FOLLOW_PATH")
    if c is None:
        c = drop.constraints.new(type="FOLLOW_PATH")
        c.name = "FOLLOW_PATH"
    c.target = path_obj
    c.use_fixed_location = True
    c.offset_factor = 0.0
    c.forward_axis = "FORWARD_Y"
    c.up_axis = "UP_Z"

    t = drop.constraints.get("TRACK_TO")
    if t is None:
        t = drop.constraints.new(type="TRACK_TO")
        t.name = "TRACK_TO"
    t.target = path_obj
    t.track_axis = "TRACK_NEGATIVE_Z"
    t.up_axis = "UP_Y"

    print("[AudioV] DROP rig ready (constraints set).")
    return drop


def main() -> int:
    ap = argparse.ArgumentParser(prog="audiov_step2")
    ap.add_argument("--midi", required=True)
    ap.add_argument("--out", required=False)
    ap.add_argument("--time-scale", type=float, default=1.0)
    ap.add_argument("--pitch-scale", type=float, default=0.12)
    ap.add_argument("--make-path", action="store_true")
    args = ap.parse_args(_argv_after_double_dash(sys.argv))

    notes = parse_midi_notes(args.midi)
    notes, pmin, pmax = normalize_notes(notes)

    build_piano_roll(
        notes,
        pitch_min=pmin,
        time_scale=args.time_scale,
        pitch_scale=args.pitch_scale,
    )

    if args.make_path:
        path_obj = build_path_curve_from_notes(
            notes,
            pitch_min=pmin,
            time_scale=args.time_scale,
            pitch_scale=args.pitch_scale,
        )
        ensure_drop_rig(path_obj)

    if args.out:
        outp = _Path(args.out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(outp))
        print(f"[AudioV] Saved: {outp}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
