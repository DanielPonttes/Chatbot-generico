"""Catálogo versionado das missões do agente de notificações.

O JSON é uma normalização da matriz ``MissõesXnotificaçõesV3.docx``. Ele
descreve a intenção de produto e a origem de cada variável, mas não substitui
os templates técnicos carregados por ``persona_service``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


_MISSION_CATALOG_PATH = Path(__file__).with_name("notification_missions.json")
MissionExecutionStatus = Literal["mapped_template", "catalog_only"]


class NotificationMissionNotFoundError(ValueError):
    """A missão solicitada não existe no catálogo versionado."""


class NotificationMissionDefinition(BaseModel):
    """Uma missão normalizada a partir do documento de produto."""

    mission_id: str = Field(..., min_length=1, pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    name: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    subtype: str = Field(..., min_length=1)
    template_id: str | None = Field(
        default=None,
        description="ID do template técnico atual, quando existe mapeamento exato.",
    )
    execution_status: MissionExecutionStatus
    example: str = Field(..., min_length=1)
    component_inputs: list[str] = Field(default_factory=list)
    agent_inputs: list[str] = Field(default_factory=list)
    context_variables: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_context_ownership(self) -> "NotificationMissionDefinition":
        expected = list(dict.fromkeys(self.component_inputs + self.agent_inputs))
        if expected != self.context_variables:
            raise ValueError(
                "context_variables deve preservar a união ordenada de "
                "component_inputs e agent_inputs"
            )
        if self.execution_status == "mapped_template" and not self.template_id:
            raise ValueError("missões mapped_template precisam de template_id")
        if self.execution_status == "catalog_only" and self.template_id:
            raise ValueError("missões catalog_only não podem declarar template_id")
        return self


class NotificationMissionCatalog(BaseModel):
    """Documento de catálogo carregado no startup e exposto pela API."""

    catalog_version: str = Field(..., min_length=1)
    source_document: str = Field(..., min_length=1)
    mission_count: int = Field(..., ge=0)
    missions: list[NotificationMissionDefinition]

    @model_validator(mode="after")
    def validate_catalog(self) -> "NotificationMissionCatalog":
        ids = [mission.mission_id for mission in self.missions]
        if self.mission_count != len(ids):
            raise ValueError("mission_count não corresponde à quantidade de missões")
        if len(ids) != len(set(ids)):
            raise ValueError("mission_id duplicado no catálogo")
        return self


def _load_catalog(path: Path = _MISSION_CATALOG_PATH) -> NotificationMissionCatalog:
    if not path.exists():
        raise FileNotFoundError(f"Catálogo de missões não encontrado: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        catalog = NotificationMissionCatalog.model_validate(raw)

        # Mantém a fonte de produto e o catálogo técnico sincronizados. O
        # import local evita acoplamento durante a definição dos modelos e
        # torna qualquer drift um erro explícito de inicialização.
        from app.services.persona_service import PersonaService

        runtime_template_ids = {
            notification_type.id
            for notification_type in PersonaService.get_notification_types()
        }
        missing_template_ids = sorted(
            {
                mission.template_id
                for mission in catalog.missions
                if mission.execution_status == "mapped_template"
                and mission.template_id not in runtime_template_ids
            }
        )
        if missing_template_ids:
            raise ValueError(
                "template_id(s) de missão sem registro técnico: "
                + ", ".join(missing_template_ids)
            )

        return catalog
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Catálogo de missões inválido em {path.name}: {exc}") from exc


NOTIFICATION_MISSION_CATALOG = _load_catalog()


def get_notification_missions() -> list[NotificationMissionDefinition]:
    """Retorna as missões em ordem estável do documento de origem."""
    return NOTIFICATION_MISSION_CATALOG.missions


def get_notification_mission_by_id(mission_id: str) -> NotificationMissionDefinition:
    """Resolve uma missão ou informa um erro de domínio estável."""
    mission = next(
        (item for item in NOTIFICATION_MISSION_CATALOG.missions if item.mission_id == mission_id),
        None,
    )
    if mission is None:
        raise NotificationMissionNotFoundError(
            f"Missão '{mission_id}' não encontrada no catálogo."
        )
    return mission
