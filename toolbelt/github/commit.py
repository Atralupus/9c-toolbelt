from typing import List, Optional, Tuple

import structlog

from toolbelt.client.github import GithubClient
from toolbelt.types import Network, RepoInfos
from toolbelt.utils.parse import latest_tag

logger = structlog.get_logger(__name__)


def get_latest_commit_hash_from_branch(
    github_client: GithubClient, branch: str
) -> str:
    ref = f"heads/{branch}"
    r = github_client.get_ref(ref)
    return r["object"]["sha"]


def get_latest_commits(
    github_client: GithubClient,
    network: Network,
    rc: int,
    repos: List[Tuple[str, str]],
    *,
    launcher_commit: Optional[str] = None,
    player_commit: Optional[str] = None,
):
    repo_infos: RepoInfos = []
    for repo, branch in repos:
        github_client.repo = repo
        ref = f"heads/{branch}"

        if network == "internal":
            r = github_client.get_ref(ref)

            if launcher_commit and repo == "9c-launcher":
                commit = launcher_commit
            elif player_commit and repo == "NineChronicles":
                commit = player_commit
            else:
                commit = r["object"]["sha"]
            tag = None
        elif network == "main":
            tags = []
            for v in github_client.get_tags(per_page=100):
                tags.extend(v)
            tag, commit = latest_tag(
                tags, rc, prefix=create_tag_prefix(network)
            )
        repo_infos.append((repo, tag, commit))

        logger.info(f"Found latest commit", repo=repo, tag=tag, commit=commit)

    return repo_infos


def create_tag_prefix(network: Network) -> str:
    prefix = ""

    if network != "main":
        prefix += f"{network}-"

    return prefix
