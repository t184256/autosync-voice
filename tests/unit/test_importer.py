# SPDX-FileCopyrightText: 2024 Alexander Sosedkin <monk@unboiled.info>
# SPDX-License-Identifier: GPL-3.0

"""Test pieces of importer module."""

from autosync_voice.importer import rename


def test_rename() -> None:
    """Test some of the rename() conversion."""
    assert rename('240230_0203.WAV') == ('2024-02-30', '0203')
    assert rename('240230_0203_01.wav') == ('2024-02-30', '0203n1')
    assert rename('240230_0203_21.WAV') == ('2024-02-30', '0203n21')
    assert rename('2024-02-30 19.04.12.flac') == ('2024-02-30', '190412')
    d, n = rename('something.ogg')
    assert d.startswith(('19', '20'))
    assert n == 'unknown-something.ogg'
