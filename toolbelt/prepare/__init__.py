import shutil
from typing import Optional

import typer

from toolbelt.constants import OUTPUT_DIR
from toolbelt.utils.typer import network_arg

from .prepare import prepare_release

prepare_app = typer.Typer()


@prepare_app.command()
def release(
    network: str = network_arg,
    rc_number: int = typer.Argument(...),
    deploy_number: int = typer.Argument(...),
    launcher_commit: Optional[str] = None,
    player_commit: Optional[str] = None,
    slack_channel: Optional[str] = None,
    dry_run: bool = False,
):
    """
    Run internal release script
    """

    # Cleanup output dir
    try:
        shutil.rmtree(OUTPUT_DIR)
    except FileNotFoundError:
        pass

    return prepare_release(
        network,  # type:ignore
        rc_number,
        deploy_number,
        launcher_commit=launcher_commit,
        player_commit=player_commit,
        slack_channel=slack_channel,
        dry_run=dry_run,
    )


__all__ = ["prepare_app"]
