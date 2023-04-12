from typing import Optional

import typer

from toolbelt.utils.typer import network_arg, platforms_arg

from .release_player import release as release_player
from .release_launcher import release as release_launcher

release_app = typer.Typer()


@release_app.command()
def player(
    commit_hash: str,
    version: int,
    network: str = network_arg,
    platform: str = platforms_arg,
    signing: bool = False,
    slack_channel: Optional[str] = None,
):
    release_player(
        commit_hash,
        platform,  # type:ignore
        version,
        network,  # type:ignore
        signing,
        slack_channel,
    )


@release_app.command()
def launcher(
    commit_hash: str,
    version: int,
    network: str = network_arg,
    platform: str = platforms_arg,
    signing: bool = False,
    slack_channel: Optional[str] = None,
):
    release_launcher(
        commit_hash,
        platform,  # type:ignore
        version,
        network,  # type:ignore
        signing,
        slack_channel,
    )
