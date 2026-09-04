from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class ModuleManifest:
    """Descrição estável de um módulo vertical do monólito.

    ``kind`` é deliberadamente aberto. Novos motores, submódulos e serviços
    transversais podem ser registrados sem alterar o kernel.
    """

    module_id: str
    name: str
    kind: str = "domain"
    version: str = "1"
    owns_tables: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    instance: Any | None = field(default=None, compare=False, repr=False)

    def public(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.module_id,
            "name": self.name,
            "kind": self.kind,
            "version": self.version,
            "owns_tables": list(self.owns_tables),
            "dependencies": list(self.dependencies),
            "capabilities": list(self.capabilities),
        }
        if self.instance is not None and hasattr(self.instance, "health"):
            try:
                result["health"] = self.instance.health()
            except Exception as error:
                result["health"] = {"status": "degraded", "error": str(error)}
        return result


class ModuleRegistry:
    """Registro extensível; não existe contagem fixa de motores ou serviços."""

    def __init__(self, modules: Iterable[ModuleManifest] = ()) -> None:
        self._modules: dict[str, ModuleManifest] = {}
        for module in modules:
            self.register(module)

    def register(self, module: ModuleManifest, *, replace: bool = False) -> ModuleManifest:
        module_id = str(module.module_id or "").strip()
        if not module_id:
            raise ValueError("Todo módulo precisa de um identificador.")
        if module_id in self._modules and not replace:
            raise ValueError(f"Módulo já registrado: {module_id}")
        self._modules[module_id] = module
        self.validate(check_dependencies=False)
        return module

    def get(self, module_id: str) -> ModuleManifest:
        try:
            return self._modules[str(module_id)]
        except KeyError as error:
            raise KeyError(f"Módulo não registrado: {module_id}") from error

    def all(self) -> tuple[ModuleManifest, ...]:
        return tuple(self._modules.values())

    def validate(self, *, check_dependencies: bool = True) -> None:
        owners: dict[str, str] = {}
        for module in self._modules.values():
            for table in module.owns_tables:
                previous = owners.get(table)
                if previous and previous != module.module_id:
                    raise ValueError(
                        f"A tabela {table!r} possui dois proprietários: {previous} e {module.module_id}."
                    )
                owners[table] = module.module_id
        if not check_dependencies:
            return
        known = set(self._modules)
        for module in self._modules.values():
            missing = sorted(set(module.dependencies) - known)
            if missing:
                raise ValueError(f"Dependências ausentes em {module.module_id}: {', '.join(missing)}")

    def table_owner(self, table: str) -> str | None:
        for module in self._modules.values():
            if table in module.owns_tables:
                return module.module_id
        return None

    def public(self) -> dict[str, Any]:
        modules = [module.public() for module in self.all()]
        return {
            "schema": "questflow.modules.v1",
            "module_count": len(modules),
            "extensible": True,
            "modules": modules,
        }
