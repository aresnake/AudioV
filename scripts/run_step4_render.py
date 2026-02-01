from __future__ import annotations

import sys
from pathlib import Path

import bpy


def _argv_after_double_dash(argv: list[str]) -> list[str]:
    if "--" in argv:
        return argv[argv.index("--") + 1 :]
    return []


def _detect_engine() -> str:
    # Prefer EEVEE Next if present, else EEVEE, else CYCLES.
    # Blender 5.0 uses BLENDER_EEVEE_NEXT name for Eevee Next.
    items = {it.identifier for it in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    if "BLENDER_EEVEE_NEXT" in items:
        return "BLENDER_EEVEE_NEXT"
    if "BLENDER_EEVEE" in items:
        return "BLENDER_EEVEE"
    if "CYCLES" in items:
        return "CYCLES"
    # Fallback: pick first
    return next(iter(items))


def _apply_render_settings(mp4_path: Path, *, engine: str, use_gpu: bool = False) -> None:
    scn = bpy.context.scene
    scn.render.engine = engine

    # Basic quality sane defaults for preview
    scn.render.resolution_x = 1920
    scn.render.resolution_y = 1080
    scn.render.resolution_percentage = 100

    # Output
    scn.render.image_settings.file_format = "FFMPEG"
    scn.render.filepath = str(mp4_path)

    ff = scn.render.ffmpeg
    ff.format = "MPEG4"
    ff.codec = "H264"
    ff.constant_rate_factor = "MEDIUM"
    ff.ffmpeg_preset = "GOOD"
    ff.gopsize = 12
    ff.use_max_b_frames = True

    # If you want audio later, we can set:
    # ff.audio_codec = "AAC"

    # Eevee/Cycles specific (keep minimal)
    if engine in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}:
        ee = scn.eevee
        # Avoid setting optional props that may not exist across builds
        for k, v in [
            ("taa_render_samples", 64),
            ("use_taa_reprojection", True),
        ]:
            if hasattr(ee, k):
                try:
                    setattr(ee, k, v)
                except Exception:
                    pass

    if engine == "CYCLES":
        cy = scn.cycles
        # Conservative defaults
        if hasattr(cy, "samples"):
            cy.samples = 64
        if hasattr(cy, "use_adaptive_sampling"):
            cy.use_adaptive_sampling = True
        if use_gpu:
            # Best-effort GPU enable. If it fails, it will still render on CPU.
            try:
                cy.device = "GPU"
            except Exception:
                pass


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="audiov_step4_render")
    ap.add_argument("--in", dest="inp", required=True, help="Input .blend")
    ap.add_argument("--out", dest="outp", required=True, help="Output .mp4 path")
    ap.add_argument("--engine", default="AUTO", help="AUTO | BLENDER_EEVEE_NEXT | BLENDER_EEVEE | CYCLES")
    ap.add_argument("--fps", type=int, default=None, help="Override fps (optional)")
    ap.add_argument("--frame-start", type=int, default=None)
    ap.add_argument("--frame-end", type=int, default=None)
    args = ap.parse_args(_argv_after_double_dash(sys.argv))

    inp = Path(args.inp)
    outp = Path(args.outp)
    outp.parent.mkdir(parents=True, exist_ok=True)

    # Load blend
    bpy.ops.wm.open_mainfile(filepath=str(inp))

    scn = bpy.context.scene
    if args.fps is not None:
        scn.render.fps = args.fps
    if args.frame_start is not None:
        scn.frame_start = args.frame_start
    if args.frame_end is not None:
        scn.frame_end = args.frame_end

    if args.engine == "AUTO":
        engine = _detect_engine()
    else:
        engine = args.engine

    _apply_render_settings(outp, engine=engine)

    print(f"[AudioV] Render engine: {engine}")
    print(f"[AudioV] Frames: {scn.frame_start}..{scn.frame_end} @ {scn.render.fps} fps")
    print(f"[AudioV] Output: {outp}")

    bpy.ops.render.render(animation=True)

    print("[AudioV] Render done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
