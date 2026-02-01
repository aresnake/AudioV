from __future__ import annotations

import sys
import subprocess
from pathlib import Path

import bpy


def _argv_after_double_dash(argv: list[str]) -> list[str]:
    if "--" in argv:
        return argv[argv.index("--") + 1 :]
    return []


def _detect_engine() -> str:
    items = {it.identifier for it in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    if "BLENDER_EEVEE_NEXT" in items:
        return "BLENDER_EEVEE_NEXT"
    if "BLENDER_EEVEE" in items:
        return "BLENDER_EEVEE"
    if "CYCLES" in items:
        return "CYCLES"
    return next(iter(items))


def _has_ffmpeg_format_runtime() -> bool:
    # IMPORTANT: must query the runtime enum on the actual ImageFormatSettings instance
    scn = bpy.context.scene
    prop = scn.render.image_settings.bl_rna.properties.get("file_format")
    if not prop:
        return False
    ids = {it.identifier for it in prop.enum_items}
    return "FFMPEG" in ids


def _find_ffmpeg() -> str | None:
    import shutil
    return shutil.which("ffmpeg")


def _apply_common_settings(*, engine: str) -> None:
    scn = bpy.context.scene
    scn.render.engine = engine
    scn.render.resolution_x = 1920
    scn.render.resolution_y = 1080
    scn.render.resolution_percentage = 100


def _apply_video_settings(mp4_path: Path) -> None:
    scn = bpy.context.scene
    scn.render.image_settings.file_format = "FFMPEG"
    scn.render.filepath = str(mp4_path)

    ff = scn.render.ffmpeg
    ff.format = "MPEG4"
    ff.codec = "H264"
    ff.constant_rate_factor = "MEDIUM"
    ff.ffmpeg_preset = "GOOD"
    ff.gopsize = 12
    ff.use_max_b_frames = True


def _apply_png_sequence_settings(seq_dir: Path) -> None:
    scn = bpy.context.scene
    seq_dir.mkdir(parents=True, exist_ok=True)

    # Blender writes frame_0001.png when filepath is a prefix
    scn.render.filepath = str(seq_dir / "frame_")
    scn.render.image_settings.file_format = "PNG"

    if hasattr(scn.render.image_settings, "color_mode"):
        scn.render.image_settings.color_mode = "RGBA"
    if hasattr(scn.render.image_settings, "compression"):
        scn.render.image_settings.compression = 15


def _encode_mp4_from_png_seq(ffmpeg: str, seq_dir: Path, mp4_path: Path, fps: int) -> None:
    inp = str(seq_dir / "frame_%04d.png")
    mp4_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg,
        "-y",
        "-framerate",
        str(int(fps)),
        "-i",
        inp,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "18",
        "-preset",
        "medium",
        str(mp4_path),
    ]
    print("[AudioV] Encoding MP4 via ffmpeg:")
    print(" ".join(cmd))
    subprocess.check_call(cmd)


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="audiov_step4_render")
    ap.add_argument("--in", dest="inp", required=True, help="Input .blend")
    ap.add_argument("--out", dest="outp", required=True, help="Output .mp4 (PNG fallback)")
    ap.add_argument("--engine", default="AUTO", help="AUTO | BLENDER_EEVEE_NEXT | BLENDER_EEVEE | CYCLES")
    ap.add_argument("--fps", type=int, default=None)
    ap.add_argument("--frame-start", type=int, default=None)
    ap.add_argument("--frame-end", type=int, default=None)
    ap.add_argument("--no-encode", action="store_true")
    args = ap.parse_args(_argv_after_double_dash(sys.argv))

    inp = Path(args.inp)
    outp = Path(args.outp)

    bpy.ops.wm.open_mainfile(filepath=str(inp))

    scn = bpy.context.scene
    if args.fps is not None:
        scn.render.fps = args.fps
    if args.frame_start is not None:
        scn.frame_start = args.frame_start
    if args.frame_end is not None:
        scn.frame_end = args.frame_end

    engine = _detect_engine() if args.engine == "AUTO" else args.engine
    _apply_common_settings(engine=engine)

    print(f"[AudioV] Render engine: {engine}")
    print(f"[AudioV] Frames: {scn.frame_start}..{scn.frame_end} @ {scn.render.fps} fps")

    # MP4 direct only if runtime enum supports it
    if outp.suffix.lower() == ".mp4" and _has_ffmpeg_format_runtime():
        _apply_video_settings(outp)
        print(f"[AudioV] Video output (direct): {outp}")
        bpy.ops.render.render(animation=True)
        print("[AudioV] Render done (mp4).")
        return 0

    # Fallback: PNG sequence
    seq_dir = outp.parent / (outp.stem + "_png")
    _apply_png_sequence_settings(seq_dir)
    print(f"[AudioV] Direct MP4 not available -> rendering PNG sequence in: {seq_dir}")
    bpy.ops.render.render(animation=True)
    print("[AudioV] Render done (png sequence).")

    if args.no_encode:
        print("[AudioV] Encoding skipped (--no-encode).")
        return 0

    ff = _find_ffmpeg()
    if ff is None:
        print("[AudioV] ffmpeg.exe not found on PATH.")
        print("[AudioV] To encode manually, run:")
        print(f'ffmpeg -y -framerate {scn.render.fps} -i "{seq_dir / "frame_%04d.png"}" -c:v libx264 -pix_fmt yuv420p -crf 18 -preset medium "{outp}"')
        return 0

    _encode_mp4_from_png_seq(ff, seq_dir, outp, fps=scn.render.fps)
    print(f"[AudioV] Encoded: {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
