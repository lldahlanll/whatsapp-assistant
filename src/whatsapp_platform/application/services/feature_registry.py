"""FeatureRegistry for managing pluggable feature modules."""

import structlog

from whatsapp_platform.application.interfaces.container import IContainer
from whatsapp_platform.application.interfaces.feature_module import IFeatureModule

logger = structlog.get_logger()


class FeatureRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, IFeatureModule] = {}

    def register(self, module: IFeatureModule) -> None:
        if module.name in self._modules:
            logger.warning(
                "Overwriting already registered feature module", name=module.name
            )
        self._modules[module.name] = module
        logger.info("Registered feature module", name=module.name)

    async def initialize_all(self, container: IContainer) -> None:
        for name, module in self._modules.items():
            logger.info("Initializing feature module", name=name)
            await module.initialize(container)

    async def shutdown_all(self) -> None:
        for name, module in self._modules.items():
            logger.info("Shutting down feature module", name=name)
            await module.shutdown()

    @property
    def modules(self) -> list[IFeatureModule]:
        return list(self._modules.values())
