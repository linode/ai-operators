import logging
import sys
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Iterable, Generator

from attrs import define
from kfp.dsl.base_component import BaseComponent

logger = logging.getLogger(__name__)


@define
class PipelineVersion:
    func: BaseComponent
    version: str


def load_module(file_path: Path) -> ModuleType:
    """
    Loads a module from source.
    """
    parent_dir = str(file_path.parent)
    module_name = file_path.name.removesuffix(".py")
    logger.info(f"Loading module {module_name}.")
    sys.path.append(parent_dir)
    try:
        module = import_module(module_name)
    finally:
        sys.path.remove(parent_dir)
    return module


def get_pipeline_items(
    paths: Iterable[Path], match_pattern="**/*.py"
) -> Generator[PipelineVersion]:
    for path in paths:
        if path.match(match_pattern):
            logger.debug(f"Processing {path}")
            module = load_module(path)
            name = getattr(module, "PIPELINE_FUNC_NAME", module.__name__)
            version = getattr(module, "PIPELINE_VERSION", None)
            pipeline_component = getattr(module, name)
            yield PipelineVersion(pipeline_component, version)
        else:
            logger.debug(f"Skipping {path}")
