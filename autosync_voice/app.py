# SPDX-FileCopyrightText: 2024 Alexander Sosedkin <monk@unboiled.info>
# SPDX-License-Identifier: GPL-3.0

"""Main module of autosync_voice."""

import logging
import time
import tomllib
import typing
from pathlib import Path

import click
import structlog
from click_default_group import DefaultGroup  # type: ignore[import-untyped]

import autosync_voice.devices
import autosync_voice.export
import autosync_voice.importer
import autosync_voice.improve
import autosync_voice.matchmake
import autosync_voice.processed_list
import autosync_voice.sync

if typing.TYPE_CHECKING:
    from autosync_voice.config import Config

    F = typing.TypeVar('F', bound=typing.Callable[..., typing.Any])


@click.group(
    cls=DefaultGroup,
    default='do-everything',
    default_if_no_args=True,
)
@click.option(
    '--config',
    envvar='AUTOSYNC_VOICE_CONFIG',
    default='config.toml',
    type=click.Path(exists=True),
)
@click.option('--debug', default=False, is_flag=True)
@click.pass_context
def cli(ctx: click.Context, config: str, debug: bool) -> None:  # noqa: FBT001
    """`autosync_voice` command-line utility."""
    # Parse and store config
    config_dict = tomllib.loads(Path(config).read_text())
    cfg = typing.cast('autosync_voice.config.Config', config_dict)
    cfg = autosync_voice.config.validate(cfg)
    ctx.obj = cfg

    # Set up logging
    if not debug:
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        )


_command: typing.Callable[['F'], 'F'] = cli.command


@_command
@click.pass_context
def detect_devices(ctx: click.Context) -> None:
    """Detect devices from config."""
    config: autosync_voice.config.Config = ctx.obj
    autosync_voice.devices.detect_devices(config)


def _do_everything(config: 'Config') -> None:
    log = structlog.get_logger()
    devices = autosync_voice.devices.detect_devices(config)
    for device in devices:
        if device.is_imported(config):
            log.debug('skipping not re-plugged', device=device.name)
            click.echo(f'{device.name} has already been imported, skipping...')
            continue
        click.echo(f'{device.name} has been newly plugged in')
        log.debug('processing newly plugged', device=device.name)
        mountpoint = device.check_mount()
        autosync_voice.importer.import_files(
            mountpoint,
            device.name,
            config['devices'][device.name]['glob'],
            Path(config['storage']['raw']),
        )
        device.mark_imported(config)
        device.umount()
    _sync_all(config)
    _export_all(config)
    _improve_all(config)


@_command
@click.pass_context
def do_everything(ctx: click.Context) -> None:
    """Do everything: importing, merging, de-noising, transcoding..."""
    config: autosync_voice.config.Config = ctx.obj
    _do_everything(config)


@_command
@click.pass_context
def lurk(ctx: click.Context) -> typing.NoReturn:
    """Lurk indefinitely, check devices once per minute."""
    config: autosync_voice.config.Config = ctx.obj
    while True:
        _do_everything(config)
        # TBD: smarter waiting, dasbus callbacks? that'd require an event loop
        time.sleep(60)


def _matchmake(config: 'Config') -> dict[Path, dict[Path, tuple[Path, Path]]]:
    raw_dir = Path(config['storage']['raw'])
    out_dir = Path(config['storage']['raw'])
    devices = config['devices']
    return {
        day_dir: autosync_voice.matchmake.matchmake(day_dir, devices, out_dir)
        for day_dir in raw_dir.glob('20*')
    }


@_command
@click.pass_context
def matchmake(ctx: click.Context) -> None:
    """Find recordings to merge together."""
    config: autosync_voice.config.Config = ctx.obj
    for day_dir, matches in _matchmake(config).items():
        for o, (f1, f2) in matches.items():
            click.echo(f'{o.relative_to(day_dir)} = {f1.stem} + {f2.stem}')


def _sync_all(config: 'Config') -> None:
    for matches in _matchmake(config).values():
        for o, (f1, f2) in matches.items():
            if not o.exists():
                autosync_voice.sync.sync(o, f1, f2)


@_command
@click.pass_context
def sync_all(ctx: click.Context) -> None:
    """Sync together and merge all eligible pairs of recordings."""
    config: autosync_voice.config.Config = ctx.obj
    _sync_all(config)


@_command
@click.argument('out', type=click.Path(exists=False))
@click.argument('in_left', type=click.Path(exists=True))
@click.argument('in_right', type=click.Path(exists=True))
def sync(out: str, in_left: str, in_right: str) -> None:
    """Sync together and merge a pair of recordings."""
    autosync_voice.sync.sync(Path(out), Path(in_left), Path(in_right))


def _export_all(config: 'Config') -> None:
    config_storage = config['storage']
    for f in Path(config_storage['raw']).rglob('*.flac'):
        r = f.relative_to(f.parent.parent.parent)
        o = (Path(config_storage['processed']) / r).with_suffix('.opus')
        if not autosync_voice.processed_list.is_processed(config_storage, o):
            click.echo(f'exporting to {o}')
            autosync_voice.export.export(o, f)
            autosync_voice.processed_list.mark_processed(config_storage, o)


@_command
@click.pass_context
def export_all(ctx: click.Context) -> None:
    """Export all recordings that were not exported yet."""
    config: autosync_voice.config.Config = ctx.obj
    _export_all(config)


@_command
@click.argument('out', type=click.Path(exists=False))
@click.argument('inp', type=click.Path(exists=True))
def export(out: str, inp: str) -> None:
    """Export a recording."""
    autosync_voice.export.export(Path(out), Path(inp))


def _improve_all(config: 'Config') -> None:
    config_storage = config['storage']
    for f in Path(config_storage['processed']).rglob('*.opus'):
        if str(f).endswith('.i.opus'):
            continue
        i = f.with_suffix('.i.opus')
        if not autosync_voice.processed_list.is_processed(config_storage, i):
            click.echo(f'improving to {i}')
            autosync_voice.improve.improve(i, f)
            autosync_voice.processed_list.mark_processed(config_storage, i)


@_command
@click.pass_context
def improve_all(ctx: click.Context) -> None:
    """Improve all yet unprocessed pairs of recordings (de-noise, etc)."""
    config: autosync_voice.config.Config = ctx.obj
    _improve_all(config)


@_command
@click.argument('out', type=click.Path(exists=False))
@click.argument('inp', type=click.Path(exists=True))
def improve(out: str, inp: str) -> None:
    """Improve a recording (de-noise, etc)."""
    autosync_voice.improve.improve(Path(out), Path(inp))


if __name__ == '__main__':
    cli()
