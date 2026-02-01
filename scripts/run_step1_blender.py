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

from audiov.midi_sheet import parse_midi_notes, normalize_notes


def _argv_after_double_dash(argv: list[str]) -> list[str]:
    # Blender passes its own args. Convention: user args are after "--"
    if "--" in argv:
        return argv[argv.index("--") + 1 :]
    return []


def _ensure_collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def _clear_collection(col: bpy.types.Collection) -> None:
    for o in list(col.objects):
        col.objects.unlink(o)
        if o.users == 0:
            bpy.data.objects.remove(o)


def build_piano_roll(
    midi_path: str,
    *,
    collection_name: str = "MIDI_SHEET",
    time_scale: float = 1.0,
    pitch_scale: float = 0.1,
    bar_height: float = 0.06,
    velocity_scale: float = 1.0,
) -> None:
    notes = parse_midi_notes(midi_path)
    notes, pmin, pmax = normalize_notes(notes)

    col = _ensure_collection(collection_name)
    _clear_collection(col)

    if not notes:
        print("[AudioV] No notes found.")
        return

    mat = bpy.data.materials.get("MAT_MIDI_NOTE")
    if mat is None:
        mat = bpy.data.materials.new("MAT_MIDI_NOTE")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf and "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = 1.0

    import bmesh

    for i, n in enumerate(notes):
        start = n.start_s * time_scale
        dur = max((n.end_s - n.start_s) * time_scale, 1e-6)
        y = (n.pitch - pmin) * pitch_scale

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

    print(f"[AudioV] Built piano roll: {len(notes)} notes | pitch {pmin}..{pmax}")


def main() -> int:
    ap = argparse.ArgumentParser(prog="audiov_step1")
    ap.add_argument("--midi", required=True)
    ap.add_argument("--out", required=False)
    ap.add_argument("--time-scale", type=float, default=1.0)
    ap.add_argument("--pitch-scale", type=float, default=0.1)

    user_argv = _argv_after_double_dash(sys.argv)
    args = ap.parse_args(user_argv)

    build_piano_roll(args.midi, time_scale=args.time_scale, pitch_scale=args.pitch_scale)

    if args.out:
        outp = _Path(args.out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(outp))
        print(f"[AudioV] Saved: {outp}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
