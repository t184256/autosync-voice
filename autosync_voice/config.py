# SPDX-FileCopyrightText: 2024 Alexander Sosedkin <monk@unboiled.info>
# SPDX-License-Identifier: GPL-3.0

"""A module that handles config-related duties."""

import typing


class Config(typing.TypedDict):
    """Type definition for the entire config."""

    storage: 'StorageConfig'
    devices: dict[str, 'DeviceConfig']


class StorageConfig(typing.TypedDict):
    """Paths to operate on."""

    raw: str
    meta: str
    processed: str
    processed_list: str


class DeviceConfig(typing.TypedDict):
    """Type definition for a device section of a config."""

    glob: str
    prefer_channel: typing.Literal['left', 'right']
    drive: dict[str, str | bool]


def validate(config: Config) -> Config:
    """Validate the config a bit (with asserts, but whatever)."""
    assert config
    assert set(config.keys()) == {'storage', 'devices'}
    assert config['storage']
    assert config['storage']['raw']
    assert config['devices']
    for device_config in config['devices'].values():
        assert 'glob' in device_config
        assert '*' in device_config['glob'] or '?' in device_config['glob']
        prefer_channel = device_config.get('prefer_channel', 'no_preference')
        assert prefer_channel in {'left', 'no_preference', 'right'}
        assert 'drive' in device_config
        assert device_config['drive']
    return config
