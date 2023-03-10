import json
import os
import shutil
import tarfile
import tempfile
import zipfile

import structlog
from py7zr import SevenZipFile
from tqdm import tqdm

from toolbelt.client import GithubClient
from toolbelt.client.aws import S3File
from toolbelt.config import config
from toolbelt.constants import OUTPUT_DIR, RELEASE_BUCKET
from toolbelt.github.workflow import Artifacts, get_artifact_urls
from toolbelt.planet.apv import Apv
from toolbelt.types import Network
from toolbelt.utils.url import build_download_url

ARTIFACTS = ["Windows.zip", "macOS.tar.gz", "Linux.tar.gz"]
artifacts_key_map = {
    "Windows.zip": "Windows",
    "macOS.tar.gz": "OSX",
    "Linux.tar.gz": "Linux",
}
ARTIFACT_BUCKET = "9c-artifacts"

unsigned_prefix = "Unsigned"
logger = structlog.get_logger(__name__)


def copy_players(
    *,
    apv: Apv,
    network: Network,
    commit: str,
    prefix: str = "",
    dry_run: bool = False,
    signing: bool = False,
):
    logger.info("[Player] Start player copy")
    github_client = GithubClient(
        config.github_token, org="planetarium", repo="NineChronicles"
    )
    release_bucket = S3File(RELEASE_BUCKET)

    urls = get_artifact_urls(
        github_client,
        commit,
    )

    with tempfile.TemporaryDirectory() as tmp_path:
        for file_name in ARTIFACTS:
            download_path = download_from_github(
                github_client, urls, artifacts_key_map[file_name], tmp_path
            )
            logger.info("[Player] Downloaded artifact", file_name=file_name)

            release_file_name = file_name

            release_path = (
                prefix
                + build_download_url(
                    "",
                    network,
                    apv.version,
                    "player",
                    commit,
                    "",
                )[1:-1]
            )

            logger.info("[Player] extract", path=download_path)

            with zipfile.ZipFile(download_path, mode="r") as archive:
                archive.extractall(path=f"{tmp_path}/{artifacts_key_map[file_name]}")

            os.rename(
                f"{tmp_path}/{artifacts_key_map[file_name]}/{file_name}",
                f"{tmp_path}/{release_file_name}",
            )

            release_bucket.upload(
                f"{tmp_path}/{release_file_name}",
                release_path,
            )
            logger.info("[Player] Upload Done", release_path=release_path)


def copy_launchers(
    *,
    apv: Apv,
    network: Network,
    commit: str,
    prefix: str = "",
    dry_run: bool = False,
):
    artifact_bucket = S3File(ARTIFACT_BUCKET)
    release_bucket = S3File(RELEASE_BUCKET)
    release_path = (
        prefix
        + build_download_url("", network, apv.version, "launcher", commit, "")[1:-1]
    )
    if network == "main":
        release_bucket.copy(
            "9c-launcher-config.json",
            f"{prefix}main/config.json",
        )

    for file_name in ARTIFACTS:
        artifact_path = f"9c-launcher/{commit}/{file_name}"

        os_name, extension = file_name.split(".", 1)

        with tempfile.TemporaryDirectory() as tmp_path:
            logger.info(f"Download launcher {artifact_path}", artifact=file_name)

            if not dry_run:
                download(
                    artifact_bucket,
                    s3_path=artifact_path,
                    path=tmp_path,
                    os_name=os_name,
                    extension=extension,
                )
                download_path = f"{tmp_path}/{file_name}"
                config_path = get_config_path(os_name)

                release_bucket.download(f"{network}/config.json", tmp_path)
                new_config = generate_new_config(network, apv, tmp_path)

                write_config(f"{tmp_path}/{config_path}", new_config)

                compress_launcher(tmp_path, os_name, extension)
                logger.info(f"Finish overwrite config", artifact=file_name)

                release_bucket.upload(
                    download_path,
                    release_path,
                )

                release_bucket.upload(f"{tmp_path}/config.json", f"{prefix}{network}")
                logger.info(
                    "Upload Finish",
                    download_path=download_path,
                    release_path=release_path,
                )
            else:
                logger.info(
                    "Skip upload launcher",
                    dry_run=dry_run,
                )


def download(s3: S3File, *, s3_path: str, path: str, os_name: str, extension: str):
    s3.download(s3_path, path)

    if extension == "tar.gz":
        zip = tarfile.open(f"{path}/{os_name}.{extension}")
        zip.extractall(f"{path}/{os_name}")
        zip.close()
    else:
        with SevenZipFile(f"{path}/{os_name}.{extension}", mode="r") as archive:
            archive.extractall(path=f"{path}/{os_name}")


def get_config_path(os_name: str):
    if os_name in ["Windows", "Linux"]:
        return f"{os_name}/resources/app/config.json"
    elif os_name == "macOS":
        return f"{os_name}/Nine Chronicles.app/Contents/Resources/app/config.json"
    else:
        raise ValueError(
            "Unsupported artifact name format: artifact name should be one of (macOS.tar.gz, Linux.tar.gz)"
        )


def write_config(config_path: str, config: str):
    with open(config_path, "w") as f:
        f.seek(0)
        json.dump(config, f, indent=4)
        f.truncate()


def compress_launcher(
    path: str,
    os_name: str,
    extension: str,
):
    if extension == "tar.gz":
        with tarfile.open(f"{path}/{os_name}.{extension}", "w:gz") as zip:
            for arcname in os.listdir(f"{path}/{os_name}"):
                name = os.path.join(path, os_name, arcname)
                zip.add(name, arcname=arcname)
    else:
        with zipfile.ZipFile(f"{path}/{os_name}.{extension}", mode="w") as archive:
            for p, _, files in os.walk(f"{path}/{os_name}"):
                for f in files:
                    filename = os.path.join(p, f)
                    archive.write(
                        filename=filename,
                        arcname=filename.removeprefix(f"{path}/{os_name}"),
                    )


def generate_new_config(network: Network, apv: Apv, path: str):
    with open(f"{path}/config.json", mode="r+") as f:
        doc = json.load(f)
        doc["AppProtocolVersion"] = apv.raw
        if network != "main":
            doc[
                "BlockchainStoreDirName"
            ] = f"9c-{network}-rc-v{apv.version}-{apv.extra['timestamp']}"
        f.seek(0)
        json.dump(doc, f, indent=4)
        f.truncate()
        return doc


def download_from_github(
    github_client: GithubClient, urls: Artifacts, key: str, dir: str
):
    file_name = f"{dir}/{key}.zip"
    res = github_client._session.get(urls[key])
    res.raise_for_status()

    total_size_in_bytes = int(res.headers.get("content-length", 0))
    progress_bar = tqdm(total=total_size_in_bytes, unit="iB", unit_scale=True)
    with open(file_name, "wb") as f:
        for chunk in res.iter_content(chunk_size=1024):
            progress_bar.update(len(chunk))
            f.write(chunk)
    progress_bar.close()

    return file_name


COPY_MACHINE = {
    "player": copy_players,
    "launcher": copy_launchers,
}
