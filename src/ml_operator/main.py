import asyncio
import os
from asyncio import Task

import kopf
from attrs import define

from .constants import RESOURCE_NAME
from .handler import Handler
from .pipelines.config import PipelineConfigLoader
from .pipelines.updater import PipelineUpdater
from .resource import AkamaiKnowledgeBase

from kubernetes_asyncio import config as k8s_config


@define
class PipelineRuntimeConfig:
    config_update_interval: int
    repo_update_interval: int
    local_repo_root: str
    config_update_task: Task = None
    repo_update_task: Task = None
    config_loader: PipelineConfigLoader = None


WATCHED_NAMESPACES = set()
HANDLER = Handler()
PIPELINE_RUNTIME_CONFIG = PipelineRuntimeConfig(
    config_update_interval=30,
    repo_update_interval=10,
    local_repo_root=os.getenv("PIPELINE_REPO_ROOT") or os.getenv("TMPDIR") or "/tmp",
)


def matches_namespaces(meta, **_):
    if not WATCHED_NAMESPACES:
        return True
    return meta["namespace"] in WATCHED_NAMESPACES


async def update_pipeline_config():
    config_loader = PIPELINE_RUNTIME_CONFIG.config_loader
    if not config_loader:
        PIPELINE_RUNTIME_CONFIG.config_loader = config_loader = PipelineConfigLoader()
    while True:
        await config_loader.update_config()
        await asyncio.sleep(PIPELINE_RUNTIME_CONFIG.config_update_interval)


async def update_repos():
    updater = None
    # Wait for config loader to be initialized
    while not updater:
        if PIPELINE_RUNTIME_CONFIG.config_loader:
            updater = PipelineUpdater(
                PIPELINE_RUNTIME_CONFIG.local_repo_root,
                PIPELINE_RUNTIME_CONFIG.config_loader,
            )
        else:
            await asyncio.sleep(1)
    while True:
        await updater.run()
        await asyncio.sleep(PIPELINE_RUNTIME_CONFIG.repo_update_interval)


@kopf.on.startup()
async def startup_fn(logger, **_):
    await k8s_config.load_config()
    loop = asyncio.get_event_loop()
    logger.info("Starting pipeline config updates.")
    PIPELINE_RUNTIME_CONFIG.config_update_task = loop.create_task(
        update_pipeline_config()
    )
    logger.info("Starting pipeline repo updates.")
    PIPELINE_RUNTIME_CONFIG.repo_update_task = loop.create_task(update_repos())
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
    if PIPELINE_RUNTIME_CONFIG.repo_update_task:
        PIPELINE_RUNTIME_CONFIG.repo_update_task.cancel()


@kopf.on.create(RESOURCE_NAME, when=matches_namespaces)
async def created(spec, meta, logger, **_):
    logger.info(f"Detected created resource {meta['name']}.")
    logger.debug(f"Spec: {spec}")
    await HANDLER.created(
        meta["namespace"], meta["name"], AkamaiKnowledgeBase.from_spec(spec)
    )


@kopf.on.update(RESOURCE_NAME, when=matches_namespaces)
async def updated(spec, meta, old, new, diff, logger, **_):
    logger.info(f"Detected updated resource {meta['name']}.")
    logger.debug(f"Spec: {spec}")
    logger.debug(f"Diff: {diff}")
    await HANDLER.updated(
        meta["namespace"], meta["name"], AkamaiKnowledgeBase.from_spec(spec)
    )


@kopf.on.delete(RESOURCE_NAME, when=matches_namespaces)
async def deleted(spec, meta, logger, **_):
    logger.info(f"Detected deleted resource {meta['name']}.")
    logger.debug(f"Spec: {spec}")
    await HANDLER.deleted(
        meta["namespace"], meta["name"], AkamaiKnowledgeBase.from_spec(spec)
    )
