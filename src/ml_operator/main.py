import os

import kopf

from .constants import RESOURCE_NAME
from .handler import Handler
from .resource import AkamaiKnowledgeBase

WATCHED_NAMESPACES = set()
HANDLER = Handler()


def matches_namespaces(meta, **_):
    if not WATCHED_NAMESPACES:
        return True
    return meta["namespace"] in WATCHED_NAMESPACES


@kopf.on.startup()
async def startup_fn(logger, **_):
    namespace_arg = os.getenv("WATCH_NAMESPACES")
    namespaces = namespace_arg.split(",") if namespace_arg else []
    if namespaces:
        WATCHED_NAMESPACES.update(namespaces)
        logger.info(f"Filtering on namespaces: {WATCHED_NAMESPACES}.")
    else:
        logger.info("Not filtering on namespaces.")


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
