# SPDX-FileCopyrightText: 2024 Alexander Sosedkin <monk@unboiled.info>
# SPDX-License-Identifier: GPL-3.0

# Uses the following StackOverflow answer: https://stackoverflow.com/a/66285894


"""Export a file, just transcoding it to opus."""

from pathlib import Path

import ffmpeg  # type: ignore[import]


def export(out: Path, inp: Path) -> None:
    """Export a file, just transcoding it to opus."""
    out.parent.mkdir(parents=True, exist_ok=True)
    stream = ffmpeg.input(inp)
    tmp = out.with_suffix('.tmp.opus')
    stream.output(str(tmp), loglevel='quiet').overwrite_output().run()
    tmp.rename(out)
