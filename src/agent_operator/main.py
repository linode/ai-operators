import asyncio
import logging
import os

import kopf
import uvloop
from kubernetes_asyncio import config as k8s_config

from .constants import RESOURCE_NAME
from .handlers import AgentHandler
from .resource import AkamaiAgent


WATCHED_NAMESPACES = set()
AGENT_HANDLER = AgentHandler()

main_logger = logging.getLogger(__name__)


def matches_namespaces(meta, **_):
    if not WATCHED_NAMESPACES:
        return True
    return meta["namespace"] in WATCHED_NAMESPACES


@kopf.on.startup()
async def startup_fn(logger, **_):
    await k8s_config.load_config()
    logger.info("Agent operator starting up.")

    namespace_arg = os.getenv("WATCH_NAMESPACES")
    namespaces = namespace_arg.split(",") if namespace_arg else []
    if namespaces:
        WATCHED_NAMESPACES.update(namespaces)
        logger.info(f"Filtering on namespaces: {WATCHED_NAMESPACES}.")
    else:
        logger.info("Not filtering on namespaces.")


@kopf.on.cleanup()
async def shutdown_fn(logger, **_):
    logger.info("Agent operator shutting down.")


@kopf.on.create(RESOURCE_NAME, when=matches_namespaces)
async def created(spec, meta, logger, **_):
    logger.info(f"Detected created resource {meta['name']}.")
    logger.debug(f"Spec: {spec}")

    await AGENT_HANDLER.created(
        meta["namespace"], meta["name"], AkamaiAgent.from_spec(spec)
    )


@kopf.on.update(RESOURCE_NAME, when=matches_namespaces)
async def updated(spec, meta, old, new, diff, logger, **_):
    logger.info(f"Detected updated resource {meta['name']}.")
    logger.debug(f"Spec: {spec}")
    logger.debug(f"Diff: {diff}")

    await AGENT_HANDLER.updated(
        meta["namespace"], meta["name"], AkamaiAgent.from_spec(spec)
    )


@kopf.on.delete(RESOURCE_NAME, when=matches_namespaces)
async def deleted(spec, meta, logger, **_):
    logger.info(f"Detected deleted resource {meta['name']}.")
    logger.debug(f"Spec: {spec}")

    await AGENT_HANDLER.deleted(
        meta["namespace"], meta["name"], AkamaiAgent.from_spec(spec)
    )


def main():
    logging.basicConfig(level=logging.DEBUG)
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    kopf.run(clusterwide=True)


if __name__ == "__main__":
    main()
