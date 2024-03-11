# SPDX-FileCopyrightText: 2024 Alexander Sosedkin <monk@unboiled.info>
# SPDX-License-Identifier: GPL-3.0

"""Importing files into storage."""

import datetime
import re
from pathlib import Path

import click
import ffmpeg  # type: ignore[import]
import structlog


def rename(name: str) -> tuple[str, str]:
    """Split the name into year and time."""
    if m := re.match(r'(\d{2})(\d{2})(\d{2})_(\d{4}).(?:wav|WAV)', name):
        # Two of my Sony recorders, most of the time
        yy, mn, dd, hhmm = m.groups()
        return f'20{yy}-{mn}-{dd}', f'{hhmm}'
    if m := re.match(r'(\d{2})(\d{2})(\d{2})_(\d{4})_(\d{2}).(wav|WAV)', name):
        # Sony when there are recordings started within the same minute
        yy, mn, dd, hhmm, n, _ = m.groups()
        n = str(int(n))  # trim leading zeroes
        return f'20{yy}-{mn}-{dd}', f'{hhmm}n{n}'
    if m := re.match(
        r'(\d{4})-(\d{2})-(\d{2}) (\d{2}).(\d{2}).(\d{2}).flac',
        name,
    ):
        # Android voice recorder
        yyyy, mn, dd, hh, mm, ss = m.groups()
        return f'{yyyy}-{mn}-{dd}', f'{hh}{mm}{ss}'
    today = (
        datetime.datetime.now(tz=datetime.UTC)
        .astimezone()
        .strftime('%Y-%m-%d')
    )
    return today, f'unknown-{name}'


def import_files(
    dev_dir: Path,
    dev_name: str,
    glob: str,
    raw_dir: Path,
) -> None:
    """Import files into raw storage, transcoding to FLAC."""
    log = structlog.get_logger()
    log.debug('import_files', dev_dir=dev_dir, glob=glob, raw_dir=raw_dir)
    for f in dev_dir.glob(glob):
        log.debug('importing', file=f)
        dirname, fname = rename(f.name)
        fname += '.flac'
        out_path = Path(raw_dir) / dirname / dev_name / fname
        out_tmp_path = out_path.with_suffix('.tmp.flac')
        out_path = out_path.with_suffix('.flac')
        log.debug('target path', target=out_path)
        assert not out_path.exists()
        click.echo(
            f'{dev_name} '
            f'importing {f.relative_to(dev_dir)} '
            f'as {out_path.relative_to(raw_dir)}',
        )

        # Transcode to tmp path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_tmp_path.unlink(missing_ok=True)
        stream = ffmpeg.input(f)
        stream = ffmpeg.output(
            stream,
            str(out_tmp_path),
            compression_level=12,
            loglevel='quiet',
        )
        ffmpeg.run(stream)

        # Check durations
        orig_duration = float(ffmpeg.probe(f)['format']['duration'])
        post_duration = float(ffmpeg.probe(out_tmp_path)['format']['duration'])
        log.debug('durations', orig=orig_duration, flac=post_duration)
        assert abs(orig_duration - post_duration) < 1e-3  # noqa: PLR2004

        # Rename
        out_tmp_path.rename(out_path)

        # Remove the original
        f.unlink()
        log.debug('imported', file=f, to=out_path)
