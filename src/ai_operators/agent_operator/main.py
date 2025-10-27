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
MAX_RETRIES = int(os.getenv("AGENT_MAX_RETRIES", "10"))

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


@kopf.on.create(RESOURCE_NAME, when=matches_namespaces, retries=MAX_RETRIES)
async def created(spec, meta, logger, retry, patch, **_):
    logger.info(
        f"Detected created resource {meta['name']} (attempt {retry + 1}/{MAX_RETRIES + 1})."
    )
    logger.debug(f"Spec: {spec}")

    try:
        patch["status"] = await AGENT_HANDLER.created(
            meta["namespace"], meta["name"], AkamaiAgent.from_spec(spec)
        )

        ready_status = await AGENT_HANDLER.wait_for_agent_ready(
            meta["namespace"], meta["name"]
        )
        if ready_status is not None:
            patch["status"] = ready_status

    except Exception as e:
        if retry >= MAX_RETRIES:
            # Last retry - mark as failed and don't re-raise
            logger.error(f"Agent {meta['name']} failed after {retry + 1} retries: {e}")
            patch["status"] = AGENT_HANDLER.mark_failed("CreateError", str(e))
        else:
            # Not the last retry - re-raise to trigger retry
            logger.warning(
                f"Agent {meta['name']} failed on attempt {retry + 1}, will retry: {e}"
            )
            raise


@kopf.on.update(RESOURCE_NAME, when=matches_namespaces, retries=MAX_RETRIES)
async def updated(spec, meta, old, new, diff, logger, retry, patch, **_):
    logger.info(
        f"Detected updated resource {meta['name']} (attempt {retry + 1}/{MAX_RETRIES + 1})."
    )
    logger.debug(f"Spec: {spec}")
    logger.debug(f"Diff: {diff}")

    try:
        patch["status"] = await AGENT_HANDLER.updated(
            meta["namespace"], meta["name"], AkamaiAgent.from_spec(spec)
        )

        ready_status = await AGENT_HANDLER.wait_for_agent_ready(
            meta["namespace"], meta["name"]
        )
        if ready_status is not None:
            patch["status"] = ready_status

    except Exception as e:
        if retry >= MAX_RETRIES:
            # Last retry - mark as failed and don't re-raise
            logger.error(
                f"Agent {meta['name']} update failed after {retry + 1} retries: {e}"
            )
            patch["status"] = AGENT_HANDLER.mark_failed("UpdateError", str(e))
        else:
            # Not the last retry - re-raise to trigger retry
            logger.warning(
                f"Agent {meta['name']} update failed on attempt {retry + 1}, will retry: {e}"
            )
            raise


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
