# SPDX-FileCopyrightText: 2024 Alexander Sosedkin <monk@unboiled.info>
# SPDX-License-Identifier: GPL-3.0

# Uses the following StackOverflow answer: https://stackoverflow.com/a/66285894


"""Calculating the shift between audio files and merging them."""

import tempfile
from pathlib import Path

import click
import ffmpeg  # type: ignore[import]
import numpy as np
import scipy.fft  # type: ignore[import]
import scipy.io  # type: ignore[import]
import structlog

SYNC_LEN = 30  # sec


def delay_pad(lbeg: Path, rbeg: Path) -> tuple[int, int, int]:
    """Calculate the delay and required end padding between two mono WAVs."""
    lrate, ldata = scipy.io.wavfile.read(lbeg)
    rrate, rdata = scipy.io.wavfile.read(rbeg)
    assert lrate == rrate
    ls = len(ldata)
    rs = len(rdata)
    padsize = ls + rs + 1
    padsize = 2 ** (int(np.log(padsize) / np.log(2)) + 1)
    lpad = np.zeros(padsize)
    lpad[:ls] = ldata
    rpad = np.zeros(padsize)
    rpad[:rs] = rdata
    corr = scipy.fft.ifft(scipy.fft.fft(lpad) * np.conj(scipy.fft.fft(rpad)))
    xmax = int(np.argmax(np.absolute(corr)))
    if xmax > padsize // 2:  # left one needs to be delayed
        delay = +(int(padsize) - xmax)
        ls_new, rs_new = delay + ls, rs
    else:  # right one needs to be delayed
        delay = -(xmax)
        ls_new, rs_new = ls, rs - delay
    len_new = max(ls_new, rs_new)
    return delay, len_new - ls_new, len_new - rs_new


def _fsec(f: float) -> str:
    return f'{f:5.3}s' if f > 0 else ' ' * 6


def sync(out: Path, lin: Path, rin: Path) -> None:  # noqa: PLR0914
    """Sync and merge together a pair of recordings."""
    log = structlog.getLogger(__name__)

    lrate = int(ffmpeg.probe(lin)['streams'][0]['sample_rate'])
    rrate = int(ffmpeg.probe(rin)['streams'][0]['sample_rate'])
    ar = max(lrate, rrate)
    action = 'downmixing'
    if lrate != rrate:
        action = 'downmixing/upsampling'
        log.debug('upsampling is required', lrate=lrate, rrate=rrate)

    with tempfile.TemporaryDirectory() as _tempdir:
        tempdir = Path(_tempdir)
        lwav, rwav = str(tempdir / 'left.wav'), str(tempdir / 'right.wav')
        lbeg, rbeg = str(tempdir / 'lbeg.wav'), str(tempdir / 'rbeg.wav')
        tmp = out.with_suffix('.tmp.flac')
        log.debug(f'{action} the left track to mono WAV...')  # noqa: G004
        ffmpeg.input(lin).output(lwav, ac=1, ar=ar, loglevel='quiet').run()
        log.debug(f'{action} the right track to mono WAV...')  # noqa: G004
        ffmpeg.input(rin).output(rwav, ac=1, ar=ar, loglevel='quiet').run()
        log.debug('extracting the beginning of the left track...')
        ffmpeg.input(lwav).output(lbeg, to=SYNC_LEN, loglevel='quiet').run()
        log.debug('extracting the beginning of the right track...')
        ffmpeg.input(rwav).output(rbeg, to=SYNC_LEN, loglevel='quiet').run()

        log.debug('calculating the delay between the tracks...')
        d, lpad, rpad = delay_pad(Path(lbeg), Path(rbeg))
        log.debug(
            'delay has been calculated',
            delay=d / ar,
            lpad=lpad / ar,
            rpad=rpad / ar,
        )
        click.echo(f'  {_fsec(+d / ar)} + {lin} + {_fsec(lpad / ar)}')
        click.echo(f'+ {_fsec(-d / ar)} + {rin} + {_fsec(rpad / ar)}')
        click.echo(f'= {out}')

        log.debug('aligning the delay between the tracks...')
        out.parent.mkdir(parents=True, exist_ok=True)
        linput = ffmpeg.input(lwav)
        rinput = ffmpeg.input(rwav)
        if d > 0:
            linput = linput.filter('adelay', f'{d}S')
        else:
            rinput = rinput.filter('adelay', f'{-d}S')
        if lpad:
            linput = linput.filter('apad', pad_len=lpad)
        if rpad:
            rinput = rinput.filter('apad', pad_len=rpad)
        stream = ffmpeg.filter(
            (linput, rinput),
            'join',
            inputs=2,
            channel_layout='stereo',
        )
        stream.output(str(tmp), loglevel='quiet').overwrite_output().run()
        tmp.rename(out)
