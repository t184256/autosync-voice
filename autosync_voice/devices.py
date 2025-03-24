# SPDX-FileCopyrightText: 2024 Alexander Sosedkin <monk@unboiled.info>
# SPDX-License-Identifier: GPL-3.0

"""Working with storage devices."""

import contextlib
import tomllib
import typing
from pathlib import Path

import click
import dasbus.connection  # type: ignore[import-untyped]
import structlog

if typing:
    from autosync_voice.config import Config


@contextlib.contextmanager
def _udisks() -> dasbus.client.proxy.InterfaceProxy:
    bus = dasbus.connection.SystemMessageBus()
    try:
        yield (
            bus,
            bus.get_proxy(
                'org.freedesktop.UDisks2',
                '/org/freedesktop/UDisks2',
            ),
        )
    finally:
        bus.disconnect()


class Device:
    """Represents a USB storage device to import the recordings from."""

    name: str
    drive: str
    time: int

    def __init__(self, name: str, drive: str, time: int) -> None:  # noqa: D107
        self.name, self.drive, self.time = name, drive, time

    def mount(self) -> Path:
        """Mount the right device somewhere."""
        log = structlog.get_logger()
        with _udisks() as (bus, udisks):

            def _get_blockdev_anew() -> tuple[str, dict[str, typing.Any]]:
                devtree = udisks.GetManagedObjects()
                assert self.drive in devtree
                blockdev = self._find_blockdev(devtree)
                assert blockdev
                return blockdev, devtree[blockdev]

            blockdev, blockdev_dict = _get_blockdev_anew()
            mountpoint = self._get_mountpoint(blockdev_dict)
            if mountpoint is not None:
                click.echo(f'{self.name} is already mounted at `{mountpoint}`')
                return mountpoint

            click.echo(f'{self.name} mounting...')
            bus.get_proxy('org.freedesktop.UDisks2', blockdev).Mount({})
            log.debug('mounted somewhere', blockdev=blockdev)
            _, blockdev_dict = _get_blockdev_anew()
            mountpoint = self._get_mountpoint(blockdev_dict)
            assert mountpoint is not None
            click.echo(f'{self.name} mounted at `{mountpoint}`')
            return mountpoint

    def check_mount(self) -> Path:
        """Mount and double-check this is the right device."""
        mountpoint = self.mount()
        ondev = tomllib.loads((mountpoint / 'autosync-voice.toml').read_text())
        assert ondev.get('device_name') == self.name
        click.echo(
            f'{self.name} has a matching `{mountpoint}/autosync-voice.toml`',
        )
        return mountpoint

    def umount(self) -> None:
        """Unmount the device."""
        log = structlog.get_logger()
        with _udisks() as (bus, udisks):
            devtree = udisks.GetManagedObjects()
            assert self.drive in devtree
            blockdev = self._find_blockdev(devtree)
            assert blockdev
            click.echo(f'{self.name} unmounting...')
            log.debug('unmounting...', blockdev=blockdev)
            dev = bus.get_proxy('org.freedesktop.UDisks2', blockdev)
            dev.Unmount({})
            log.debug('checking...', blockdev=blockdev)
            click.echo(f'{self.name} checking...')
            clean = dev.Check({})
            if not clean:
                click.echo(f'{self.name} repairing...')
                log.debug('repairing...', blockdev=blockdev, clean=clean)
                clean = dev.Repair({})
            log.debug('unmounted', blockdev=blockdev)
            click.echo(f'{self.name} unmounted {"" if clean else "un"}cleanly')

    def _find_blockdev(
        self,
        devtree: dasbus.client.proxy.InterfaceProxy,
    ) -> str | None:
        """Find the corresponding blockdev."""
        log = structlog.get_logger()
        for block, iface_dict in devtree.items():
            match iface_dict:
                case {
                    'org.freedesktop.UDisks2.Filesystem': _,
                    'org.freedesktop.UDisks2.Partition': _,
                    'org.freedesktop.UDisks2.Block': {'Drive': d},
                } if d.unpack() == self.drive:
                    log.debug('found blockdev', dev=self.name, blockdev=block)
                    return typing.cast('str', block)
        return None

    @staticmethod
    def _get_mountpoint(
        blockdev_iface_dict: dict[str, typing.Any],
    ) -> Path | None:
        """Find the corresponding mountpoint."""
        log = structlog.get_logger()
        fs = blockdev_iface_dict['org.freedesktop.UDisks2.Filesystem']
        assert 'MountPoints' in fs
        match list(fs['MountPoints']):
            case [[*pre, 0]]:
                s = bytes(pre).decode()
                log.debug('detected mountpoint', mountpoint=s)
                return Path(s)
            case []:
                log.debug('detected no mountpoints')
                return None
            case _:
                msg = 'multiple mountpoints detected'
                raise NotImplementedError(msg)

    def mark_imported(self, config: Config) -> None:
        """Remember the plugged-in time of the device."""
        timestamp_path = Path(config['storage']['meta'], 'imported', self.name)
        timestamp_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp_path.write_text(str(self.time))

    def is_imported(self, config: Config) -> bool:
        """Compare the plugged-in time with the last known one."""
        timestamp_path = Path(config['storage']['meta'], 'imported', self.name)
        if not timestamp_path.exists():
            return False
        return int(timestamp_path.read_text()) >= self.time


def detect_devices(config: Config) -> tuple[Device, ...]:
    """Find all drives/partitions matching the devices from config."""
    log = structlog.get_logger()
    with _udisks() as (_, udisks):
        devtree = udisks.GetManagedObjects().items()
    # find interesting Drives, gather Devices
    log.debug('scanning devices')
    devices = []
    for drive, iface_dict in devtree:
        if 'org.freedesktop.UDisks2.Drive' not in iface_dict:
            continue
        device_attrs = iface_dict['org.freedesktop.UDisks2.Drive']
        for device, device_config in config['devices'].items():
            log.debug('matching', drive=drive, against=device)
            match_criteria = device_config['drive']
            for k, v in match_criteria.items():
                if k not in device_attrs or device_attrs[k].unpack() != v:
                    log.debug('mismatch', key=k, value_dev=v)
                    break
            else:
                time = device_attrs['TimeMediaDetected'].unpack()
                log.debug('found', device=device, drive=drive)
                devices.append(Device(name=device, drive=drive, time=time))
                break
    return tuple(devices)
