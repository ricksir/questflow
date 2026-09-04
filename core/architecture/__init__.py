"""Kernel arquitetural do monólito modular QuestFlow.

Este pacote contém somente contratos e infraestrutura transversal. Módulos de
domínio não devem importar adapters concretos uns dos outros.
"""

from .events import DomainEvent, InternalEventBus, SelectiveEventStore
from .kernel import ArchitectureKernel
from .modules import ModuleManifest, ModuleRegistry
from .ownership import TABLE_OWNERS, module_table_catalog
from .projections import ProjectionCatalog, ProjectionDefinition

__all__ = [
    "ArchitectureKernel",
    "DomainEvent",
    "InternalEventBus",
    "ModuleManifest",
    "ModuleRegistry",
    "ProjectionCatalog",
    "ProjectionDefinition",
    "SelectiveEventStore",
    "TABLE_OWNERS",
    "module_table_catalog",
]
