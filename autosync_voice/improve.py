# SPDX-FileCopyrightText: 2024 Alexander Sosedkin <monk@unboiled.info>
# SPDX-License-Identifier: GPL-3.0

# Uses the following StackOverflow answer: https://stackoverflow.com/a/66285894


"""Calculating the shift between audio files and merging them."""

import shutil
import subprocess  # noqa: S404
import tempfile
from pathlib import Path

import ffmpeg  # type: ignore[import]


def _improve_48k(out: Path, inp: Path, tmp_dir: Path) -> None:
    tmp = tmp_dir / 'tmp.wav'
    shutil.copy(inp, tmp)  # it's in-place now for some reason
    args = ['-o', str(tmp_dir), '--pf', '-D', '-a', '10', str(tmp)]
    subprocess.run(['deepfilternet', *args], check=True)  # noqa: S603, S607
    tmp.rename(out)


def improve(out: Path, inp: Path) -> None:
    """Improve a recording (de-noise, etc)."""
    with tempfile.TemporaryDirectory() as _tempdir:
        tempdir = Path(_tempdir)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix('.tmp.opus')
        wav, imp = str(tempdir / 'mono.wav'), str(tempdir / 'imp.wav')
        ffmpeg.input(inp).output(wav, ar=48000, loglevel='quiet').run()
        _improve_48k(Path(imp), Path(wav), tempdir)
        stream = ffmpeg.input(imp)
        stream.output(str(tmp), loglevel='quiet').overwrite_output().run()
        tmp.rename(out)
