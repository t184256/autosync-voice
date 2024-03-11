# SPDX-FileCopyrightText: 2024 Alexander Sosedkin <monk@unboiled.info>
# SPDX-License-Identifier: GPL-3.0

# Uses the following StackOverflow answer: https://stackoverflow.com/a/66285894


"""Utility functions to track what's processed and what's not."""

import typing
from pathlib import Path

if typing.TYPE_CHECKING:
    from autosync_voice.config import StorageConfig


def is_processed(sconfig: 'StorageConfig', path: Path) -> bool:
    """Check whether we've already processed that file."""
    pl_path = Path(sconfig['processed_list'])
    p = path.relative_to(sconfig['processed'])
    if not pl_path.exists():
        return False
    return str(p) in Path(pl_path).read_text().strip().split('\n')


def mark_processed(sconfig: 'StorageConfig', path: Path) -> None:
    """Mark a file as already processed."""
    pl_path = Path(sconfig['processed_list'])
    p = path.relative_to(sconfig['processed'])
    with Path(pl_path).open(mode='a') as f:
        print(p, file=f)
