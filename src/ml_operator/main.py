import asyncio
import logging
import os
from asyncio import Task

import kopf
import uvloop
from attrs import define
from kubernetes_asyncio import config as k8s_config

from .constants import RESOURCE_NAME
from .handlers import KnowledgeBaseHandler
from .pipelines.config import PipelineConfigLoader
from .pipelines.downloader import PipelineDownloader, PipelineDownloadConfig
from .pipelines.updater import PipelineUpdater
from .resource import AkamaiKnowledgeBase


@define
class PipelineRuntimeConfig:
    config_update_interval: int
    source_update_interval: int
    local_source_root: str
    config_update_task: Task = None
    source_update_task: Task = None
    config_loader: PipelineConfigLoader = None


WATCHED_NAMESPACES = set()
KB_HANDLER = KnowledgeBaseHandler()
PIPELINE_RUNTIME_CONFIG = PipelineRuntimeConfig(
    config_update_interval=30,
    source_update_interval=10,
    local_source_root=os.getenv("PIPELINE_SOURCE_ROOT")
    or os.getenv("TMPDIR")
    or "/tmp",
)

main_logger = logging.getLogger(__name__)


def matches_namespaces(meta, **_):
    if not WATCHED_NAMESPACES:
        return True
    return meta["namespace"] in WATCHED_NAMESPACES


async def update_pipeline_config():
    config_loader = PIPELINE_RUNTIME_CONFIG.config_loader
    if not config_loader:
        PIPELINE_RUNTIME_CONFIG.config_loader = config_loader = PipelineConfigLoader()
    while True:
        try:
            await config_loader.update_config()
        except Exception as e:
            main_logger.error("Error during pipeline config update", exc_info=e)
        await asyncio.sleep(PIPELINE_RUNTIME_CONFIG.config_update_interval)


async def update_pipelines():
    # Wait for config loader to be initialized
    while not PIPELINE_RUNTIME_CONFIG.config_loader:
        await asyncio.sleep(1)
    updater = PipelineUpdater()
    async with PipelineDownloader(
        PipelineDownloadConfig(local_path=PIPELINE_RUNTIME_CONFIG.local_source_root)
    ) as downloader:
        while True:
            try:
                await updater.run(
                    PIPELINE_RUNTIME_CONFIG.config_loader.get_config(), downloader
                )
            except Exception as e:
                main_logger.error("Error during pipeline source update", exc_info=e)
            await asyncio.sleep(PIPELINE_RUNTIME_CONFIG.source_update_interval)


@kopf.on.startup()
async def startup_fn(logger, **_):
    await k8s_config.load_config()
    loop = asyncio.get_event_loop()
    logger.info("Starting pipeline config updates.")
    PIPELINE_RUNTIME_CONFIG.config_update_task = loop.create_task(
        update_pipeline_config()
    )
    logger.info("Starting pipeline repo updates.")
    PIPELINE_RUNTIME_CONFIG.source_update_task = loop.create_task(update_pipelines())
    namespace_arg = os.getenv("WATCH_NAMESPACES")
    namespaces = namespace_arg.split(",") if namespace_arg else []
    if namespaces:
        WATCHED_NAMESPACES.update(namespaces)
        logger.info(f"Filtering on namespaces: {WATCHED_NAMESPACES}.")
    else:
        logger.info("Not filtering on namespaces.")


@kopf.on.cleanup()
async def shutdown_fn(logger, **_):
    logger.info("Stopping pipeline config updates.")
    if PIPELINE_RUNTIME_CONFIG.config_update_task:
        PIPELINE_RUNTIME_CONFIG.config_update_task.cancel()
    logger.info("Stopping pipeline repo updates.")
    if PIPELINE_RUNTIME_CONFIG.source_update_task:
        PIPELINE_RUNTIME_CONFIG.source_update_task.cancel()


@kopf.on.create(RESOURCE_NAME, when=matches_namespaces)
async def created(spec, meta, logger, **_):
    logger.info(f"Detected created resource {meta['name']}.")
    logger.debug(f"Spec: {spec}")

    run_id = await KB_HANDLER.created(
        meta["namespace"], meta["name"], AkamaiKnowledgeBase.from_spec(spec)
    )
    await KB_HANDLER.wait_for_completion(meta["namespace"], meta["name"], run_id)


@kopf.on.update(RESOURCE_NAME, when=matches_namespaces)
async def updated(spec, meta, old, new, diff, logger, **_):
    logger.info(f"Detected updated resource {meta['name']}.")
    logger.debug(f"Spec: {spec}")
    logger.debug(f"Diff: {diff}")

    run_id = await KB_HANDLER.updated(
        meta["namespace"], meta["name"], AkamaiKnowledgeBase.from_spec(spec)
    )
    await KB_HANDLER.wait_for_completion(meta["namespace"], meta["name"], run_id)


@kopf.on.delete(RESOURCE_NAME, when=matches_namespaces)
async def deleted(spec, meta, logger, **_):
    logger.info(f"Detected deleted resource {meta['name']}.")
    logger.debug(f"Spec: {spec}")
    await KB_HANDLER.deleted(
        meta["namespace"], meta["name"], AkamaiKnowledgeBase.from_spec(spec)
    )


def main():
    logging.basicConfig(level=logging.DEBUG)
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    kopf.run(clusterwide=True)


if __name__ == "__main__":
    main()
