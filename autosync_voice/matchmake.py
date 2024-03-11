# SPDX-FileCopyrightText: 2024 Alexander Sosedkin <monk@unboiled.info>
# SPDX-License-Identifier: GPL-3.0

"""Finding recordings that look like they could be of the same thing."""

import itertools
import re
import typing
from pathlib import Path

import structlog

if typing.TYPE_CHECKING:
    from autosync_voice.config import DeviceConfig


def approx_time_in_minutes(name: str) -> int | None:
    """Deduce a start time scalar from a filename, unit is minutes."""
    if m := re.match(r'(\d{2})(\d{2}).*', name):
        hh, mm = m.groups()
        return int(hh) * 60 + int(mm)
    return None


def _outpath(out_dir: Path, path1: Path, path2: Path) -> Path:
    if path1.stem == path2.stem:
        name = path1.stem + '.flac'
    else:
        name = f'{path1.stem}-{path2.stem}.flac'
    combidir = f'{path1.parent.name}-{path2.parent.name}'
    day_dir = path1.parent.parent
    return out_dir / day_dir / combidir / name


def _files_times(day_dir: Path, device_name: str) -> dict[Path, int]:
    files_times = {
        recording: approx_time_in_minutes(recording.name)
        for recording in (day_dir / device_name).glob('*.flac')
    }
    return {f: t for f, t in files_times.items() if t is not None}


def matchmake(
    day_dir: Path,
    devices: dict[str, 'DeviceConfig'],
    out_dir: Path,
    lax_min: int = 1,
) -> dict[Path, tuple[Path, Path]]:
    """Find recordings that look like they could be of the same thing."""
    log = structlog.get_logger()
    devs_sorted = sorted(devices, key=lambda d: devices[d]['prefer_channel'])
    log.debug('matchmake', dir=day_dir, devices=devs_sorted)

    matches = {}
    for d1, d2 in itertools.combinations(devs_sorted, 2):
        for f1, t1 in _files_times(day_dir, d1).items():
            for f2, t2 in _files_times(day_dir, d2).items():
                assert t1 is not None
                assert t2 is not None
                if f1 is not f2 and abs(t1 - t2) <= lax_min:
                    matches[_outpath(out_dir, f1, f2)] = f1, f2
    return matches
