"""
Serviços para explorar integrações externas do projeto.

Inclui:
- introspecção do PostgreSQL remoto com tabelas, colunas e amostras de dados
- catálogo da API Spring Boot com endpoints confirmados e observados no Postman
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx
import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.core.config import settings

logger = logging.getLogger(__name__)


class IntegrationCatalogError(Exception):
    """Erro base para integrações externas."""


class RemoteDatabaseError(IntegrationCatalogError):
    """Erro ao consultar o PostgreSQL remoto."""


class RemoteSpringApiError(IntegrationCatalogError):
    """Erro ao consultar a API Spring Boot."""


class EndpointNotFoundError(RemoteSpringApiError):
    """Endpoint solicitado não existe no catálogo."""


class EndpointInvocationNotSupportedError(RemoteSpringApiError):
    """Endpoint existe no catálogo, mas não tem invocação automática suportada."""


TABLE_METADATA: dict[str, dict[str, Any]] = {
    "medicao": {
        "category": "telemetria",
        "relevance_score": 100,
        "relevance_reason": "Fonte principal de medições para análises e notificações energéticas.",
    },
    "parametro_valor": {
        "category": "telemetria",
        "relevance_score": 98,
        "relevance_reason": "Carrega os valores efetivos de cada parâmetro coletado por medição.",
    },
    "parametro_def": {
        "category": "telemetria",
        "relevance_score": 96,
        "relevance_reason": "Define os parâmetros configuráveis do sensor sem exigir alteração estrutural no banco.",
    },
    "sensor": {
        "category": "telemetria",
        "relevance_score": 95,
        "relevance_reason": "Liga sensores a compartimentos e tipos, base para correlacionar medições.",
    },
    "compartimento": {
        "category": "ocupacao",
        "relevance_score": 94,
        "relevance_reason": "Representa as salas/ambientes usados para consumo, presença e notificações por local.",
    },
    "presenca": {
        "category": "ocupacao",
        "relevance_score": 93,
        "relevance_reason": "Permite correlacionar ocupação real com consumo e medições ambientais.",
    },
    "pessoa": {
        "category": "usuarios",
        "relevance_score": 90,
        "relevance_reason": "Cadastro de usuários necessário para check-in, checkout e personalização de alertas.",
    },
    "tipo_de_sensor": {
        "category": "cadastro",
        "relevance_score": 82,
        "relevance_reason": "Tipifica sensores e ajuda a descobrir quais parâmetros cada sensor suporta.",
    },
    "predio": {
        "category": "estrutura",
        "relevance_score": 80,
        "relevance_reason": "Agrupa compartimentos por prédio, útil para dashboards agregados.",
    },
    "unidade": {
        "category": "estrutura",
        "relevance_score": 78,
        "relevance_reason": "Contextualiza compartimentos por unidade administrativa.",
    },
    "campus": {
        "category": "estrutura",
        "relevance_score": 76,
        "relevance_reason": "Permite segmentar análises por campus.",
    },
}


@dataclass(frozen=True)
class SpringEndpointDefinition:
    """Metadados de um endpoint remoto da API Spring."""

    id: str
    category: str
    method: str
    path_template: str
    description: str
    discovery_source: str
    relevance_score: int
    relevance_reason: str
    invoke_supported: bool = True
    side_effect: bool = False
    example_path_params: dict[str, str] = field(default_factory=dict)
    example_query_params: dict[str, str] = field(default_factory=dict)
    example_body: dict[str, Any] | list[Any] | None = None


SPRING_ENDPOINTS: tuple[SpringEndpointDefinition, ...] = (
    SpringEndpointDefinition(
        id="actuator_health",
        category="setup",
        method="GET",
        path_template="/actuator/health",
        description="Health check da API Spring Boot (helper de setup nos testes E2E).",
        discovery_source="confirmed",
        relevance_score=70,
        relevance_reason="A API restringe este endpoint (retorna 401 mesmo com JWT ADMIN), então não é invocável na prática.",
        invoke_supported=False,
    ),
    SpringEndpointDefinition(
        id="rooms_sync",
        category="bootstrap",
        method="POST",
        path_template="/api/rooms/sync",
        description="Sincroniza rooms/compartimentos migrados do Cobalto para o backend Spring.",
        discovery_source="confirmed",
        relevance_score=88,
        relevance_reason="Importante para manter a malha de rooms alinhada com a origem legada.",
        side_effect=True,
    ),
    SpringEndpointDefinition(
        id="sensors_seed_from_legacy",
        category="bootstrap",
        method="POST",
        path_template="/api/sensors/seed/from-resource",
        description="Bootstrap de sensores a partir da base legada (seed from-resource).",
        discovery_source="confirmed",
        relevance_score=84,
        relevance_reason="Relevante para povoar sensores a partir do recurso legado.",
        side_effect=True,
    ),
    SpringEndpointDefinition(
        id="pessoas_create",
        category="pessoas",
        method="POST",
        path_template="/api/pessoas",
        description="Cria uma pessoa/usuário no backend Spring.",
        discovery_source="confirmed",
        relevance_score=87,
        relevance_reason="Necessário para testes de fluxo de check-in e personalização por usuário.",
        side_effect=True,
        example_body={
            "id": "demo-user",
            "nome": "Usuario Demo",
            "email": "demo@example.com",
            "telefone": "51999999999",
            "matricula": "MAT-DEMO",
            "password": "123456",
        },
    ),
    SpringEndpointDefinition(
        id="pessoas_get",
        category="pessoas",
        method="GET",
        path_template="/api/pessoas/{pessoa_id}",
        description="Consulta uma pessoa específica pelo identificador.",
        discovery_source="confirmed",
        relevance_score=89,
        relevance_reason="Útil para validar usuários antes de acionar presença e notificações.",
        example_path_params={"pessoa_id": "ravilon"},
    ),
    SpringEndpointDefinition(
        id="pessoas_update",
        category="pessoas",
        method="PUT",
        path_template="/api/pessoas/{pessoa_id}",
        description="Atualiza uma pessoa existente.",
        discovery_source="confirmed",
        relevance_score=80,
        relevance_reason="Mantém o cadastro alinhado para testes e integração com presença.",
        side_effect=True,
        example_path_params={"pessoa_id": "ravilon"},
        example_body={
            "nome": "Ravilon A. Santos",
            "telefone": "51988887777",
        },
    ),
    SpringEndpointDefinition(
        id="presencas_checkin",
        category="presencas",
        method="POST",
        path_template="/api/presencas/checkin",
        description="Registra o check-in de uma pessoa em um compartimento.",
        discovery_source="confirmed",
        relevance_score=92,
        relevance_reason="Essencial para cruzar ocupação com medições e acionar mensagens contextuais.",
        side_effect=True,
        example_body={
            "pessoaId": "ravilon",
            "compartimentoId": "2",
            "source": "manual",
        },
    ),
    SpringEndpointDefinition(
        id="presencas_occupancy_observed",
        category="presencas",
        method="GET",
        path_template="/api/presencas/ocupacao/compartimentos/{room_id}",
        description="Consulta a ocupação atual de um compartimento.",
        discovery_source="confirmed",
        relevance_score=90,
        relevance_reason="Muito relevante para inferir ocupação atual da sala.",
        example_path_params={"room_id": "393"},
    ),
    SpringEndpointDefinition(
        id="presencas_open_observed",
        category="presencas",
        method="GET",
        path_template="/api/presencas/abertas/compartimentos/{room_id}",
        description="Lista presenças em aberto de um compartimento.",
        discovery_source="confirmed",
        relevance_score=90,
        relevance_reason="Muito relevante para monitorar ocupação em aberto.",
        example_path_params={"room_id": "393"},
    ),
    SpringEndpointDefinition(
        id="sensors_ingest_mock",
        category="mock",
        method="POST",
        path_template="/api/sensors/ingest/mock",
        description="Gera medições mockadas para um sensor e persiste no backend Spring.",
        discovery_source="confirmed",
        relevance_score=97,
        relevance_reason="Excelente para demos e desenvolvimento quando ainda não há ingestão em tempo real.",
        side_effect=True,
    ),
    SpringEndpointDefinition(
        id="sensor_measurements_list",
        category="medicoes",
        method="GET",
        path_template="/api/sensors/{sensor_external_id}/medicoes",
        description="Lista medições de um sensor pelo external id.",
        discovery_source="confirmed",
        relevance_score=100,
        relevance_reason="É o endpoint HTTP mais útil para o projeto atual, pois já devolve medições enriquecidas por sensor.",
        example_path_params={"sensor_external_id": "SII-001"},
    ),
    SpringEndpointDefinition(
        id="sensor_measurements_latest",
        category="medicoes",
        method="GET",
        path_template="/api/sensors/{sensor_external_id}/medicoes/latest",
        description="Retorna a última medição de um sensor.",
        discovery_source="confirmed",
        relevance_score=100,
        relevance_reason="Ideal para cards de status e notificações em tempo quase real.",
        example_path_params={"sensor_external_id": "SII-001"},
    ),
    SpringEndpointDefinition(
        id="room_measurements_list",
        category="medicoes",
        method="GET",
        path_template="/api/rooms/{room_id}/medicoes",
        description="Lista medições agregadas/relacionadas a um compartimento.",
        discovery_source="confirmed",
        relevance_score=99,
        relevance_reason="Permite trabalhar no nível da sala, que é o contexto central deste projeto.",
        example_path_params={"room_id": "2"},
    ),
    SpringEndpointDefinition(
        id="room_measurements_latest",
        category="medicoes",
        method="GET",
        path_template="/api/rooms/{room_id}/medicoes/latest",
        description="Retorna a última medição associada a um compartimento.",
        discovery_source="confirmed",
        relevance_score=99,
        relevance_reason="Perfeito para dashboards de salas e alertas contextuais por ambiente.",
        example_path_params={"room_id": "2"},
    ),
    SpringEndpointDefinition(
        id="presencas_checkout",
        category="presencas",
        method="POST",
        path_template="/api/presencas/checkout",
        description="Finaliza uma presença aberta por checkout explícito.",
        discovery_source="confirmed",
        relevance_score=85,
        relevance_reason="Completa o fluxo de ocupação para análise de permanência.",
        side_effect=True,
        example_body={"pessoaId": "ravilon", "compartimentoId": "2"},
    ),
    SpringEndpointDefinition(
        id="presencas_checkout_extra",
        category="presencas",
        method="POST",
        path_template="/api/presencas/checkout/by-pessoa",
        description="Checkout de presença informando apenas a pessoa (fecha a presença aberta dela).",
        discovery_source="confirmed",
        relevance_score=80,
        relevance_reason="Útil para checkout rápido sem precisar do presencaId.",
        side_effect=True,
        example_body={"pessoaId": "ravilon"},
    ),
    SpringEndpointDefinition(
        id="missoes_list",
        category="missoes",
        method="GET",
        path_template="/api/missoes",
        description="Lista missões de gamificação (filtro opcional por ativo).",
        discovery_source="confirmed",
        relevance_score=86,
        relevance_reason="Base para notificações de engajamento e missões ativas do usuário.",
        example_query_params={"ativo": "true"},
    ),
    SpringEndpointDefinition(
        id="missoes_get",
        category="missoes",
        method="GET",
        path_template="/api/missoes/{missao_id}",
        description="Detalha uma missão específica.",
        discovery_source="confirmed",
        relevance_score=78,
        relevance_reason="Permite detalhar regras da missão antes de mencioná-la em notificações.",
    ),
    SpringEndpointDefinition(
        id="pessoas_atividades_list",
        category="atividades",
        method="GET",
        path_template="/api/pessoas/{pessoa_id}/atividades",
        description="Lista atividades (missões atribuídas) de uma pessoa, com filtro opcional por status.",
        discovery_source="confirmed",
        relevance_score=91,
        relevance_reason="Mostra o andamento das missões do usuário, insumo direto para notificações personalizadas.",
        example_path_params={"pessoa_id": "admin"},
        example_query_params={"status": "PENDENTE"},
    ),
    SpringEndpointDefinition(
        id="pessoas_atividades_resumo",
        category="atividades",
        method="GET",
        path_template="/api/pessoas/{pessoa_id}/atividades/resumo",
        description="Resumo das atividades de uma pessoa (contadores por status).",
        discovery_source="confirmed",
        relevance_score=89,
        relevance_reason="Resumo compacto ideal para contextualizar notificações de engajamento.",
        example_path_params={"pessoa_id": "admin"},
    ),
    SpringEndpointDefinition(
        id="rules_parameter_defs",
        category="rules",
        method="GET",
        path_template="/api/rules/parameter-defs",
        description="Lista definições de parâmetros disponíveis para regras (filtro opcional por tipo de sensor).",
        discovery_source="confirmed",
        relevance_score=74,
        relevance_reason="Ajuda a descobrir quais métricas podem ser usadas em regras e notificações.",
        example_query_params={"tipoNome": "SII_SMART"},
    ),
)


def _table_metadata(table_name: str, columns: list[str] | None = None) -> dict[str, Any]:
    if table_name in TABLE_METADATA:
        return TABLE_METADATA[table_name]

    columns = columns or []
    normalized_columns = " ".join(
        column.casefold().replace("-", "_") for column in columns
    )

    if "timestamp" in normalized_columns or "sensor" in normalized_columns:
        return {
            "category": "telemetria",
            "relevance_score": 75,
            "relevance_reason": "Tabela aparenta guardar dados operacionais de sensores ou séries temporais.",
        }

    return {
        "category": "cadastro",
        "relevance_score": 65,
        "relevance_reason": "Tabela de apoio útil para contexto e relacionamento, mas menos central para o fluxo atual.",
    }


class RemotePostgresCatalogService:
    """Explora o PostgreSQL remoto com foco em tabelas relevantes ao projeto."""

    SENSITIVE_PREVIEW_COLUMNS = {
        "password",
        "passwd",
        "pass",
        "senha",
        "email",
        "e_mail",
        "mail",
        "telefone",
        "phone",
        "matricula",
        "cpf",
        "documento",
        "secret",
        "token",
        "auth",
        "credential",
        "credentials",
        "api_key",
        "private_key",
        "access_token",
        "refresh_token",
        "jwt",
        "hash",
    }
    SENSITIVE_PREVIEW_TOKENS = {
        "password",
        "passwd",
        "pass",
        "senha",
        "email",
        "mail",
        "telefone",
        "phone",
        "matricula",
        "cpf",
        "documento",
        "secret",
        "token",
        "auth",
        "credential",
        "credentials",
        "jwt",
        "hash",
    }

    @classmethod
    def _sanitize_preview_rows(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sanitized_rows = []
        for row in rows:
            sanitized_rows.append(
                {
                    key: "[redacted]"
                    if cls._is_sensitive_preview_column(key)
                    else value
                    for key, value in row.items()
                }
            )
        return sanitized_rows

    @classmethod
    def _is_sensitive_preview_column(cls, key: object) -> bool:
        camel_case_key = re.sub(
            r"([A-Z]+)([A-Z][a-z])", r"\1_\2", str(key)
        )
        camel_case_key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", camel_case_key)
        normalized = "".join(
            char if char.isalnum() else "_"
            for char in camel_case_key.casefold()
        ).strip("_")
        if normalized in cls.SENSITIVE_PREVIEW_COLUMNS:
            return True
        tokens = [token for token in normalized.split("_") if token]
        if any(token in cls.SENSITIVE_PREVIEW_TOKENS for token in tokens):
            return True
        return any(
            "_".join(tokens[index : index + 2]) in cls.SENSITIVE_PREVIEW_COLUMNS
            for index in range(len(tokens) - 1)
        )

    def _connect(self) -> psycopg.Connection:
        if not settings.remote_pg_password:
            raise RemoteDatabaseError(
                "REMOTE_PG_PASSWORD não está configurada. Defina a senha do PostgreSQL remoto."
            )

        try:
            return psycopg.connect(
                host=settings.remote_pg_host,
                port=settings.remote_pg_port,
                user=settings.remote_pg_user,
                password=settings.remote_pg_password,
                dbname=settings.remote_pg_database,
                connect_timeout=settings.remote_pg_connect_timeout,
                sslmode=settings.remote_pg_sslmode,
                row_factory=dict_row,
            )
        except Exception as exc:
            raise RemoteDatabaseError(
                f"Falha ao conectar no PostgreSQL remoto: {exc}"
            ) from exc

    def get_connection_info(self) -> dict[str, Any]:
        return {
            "host": settings.remote_pg_host,
            "port": settings.remote_pg_port,
            "database": settings.remote_pg_database,
            "user": settings.remote_pg_user,
            "sslmode": settings.remote_pg_sslmode,
        }

    def health(self) -> dict[str, Any]:
        query = "select current_database() as database_name, current_user as current_user"

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()

        return {
            **self.get_connection_info(),
            "status": "connected",
            "database_name": row["database_name"],
            "current_user": row["current_user"],
        }

    def list_tables(self) -> list[dict[str, Any]]:
        query = """
            with column_stats as (
                select
                    table_schema,
                    table_name,
                    count(*)::int as columns_count,
                    array_agg(column_name order by ordinal_position) as columns
                from information_schema.columns
                where table_schema not in ('pg_catalog', 'information_schema')
                group by table_schema, table_name
            ),
            row_stats as (
                select
                    n.nspname as table_schema,
                    c.relname as table_name,
                    c.reltuples::bigint as estimated_rows
                from pg_class c
                join pg_namespace n on n.oid = c.relnamespace
                where c.relkind = 'r'
            )
            select
                t.table_schema,
                t.table_name,
                coalesce(cs.columns_count, 0) as columns_count,
                cs.columns,
                rs.estimated_rows
            from information_schema.tables t
            left join column_stats cs
                on cs.table_schema = t.table_schema
                and cs.table_name = t.table_name
            left join row_stats rs
                on rs.table_schema = t.table_schema
                and rs.table_name = t.table_name
            where t.table_type = 'BASE TABLE'
              and t.table_schema not in ('pg_catalog', 'information_schema')
            order by t.table_schema, t.table_name
        """

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        tables: list[dict[str, Any]] = []
        for row in rows:
            metadata = _table_metadata(row["table_name"], row["columns"] or [])
            tables.append(
                {
                    "schema": row["table_schema"],
                    "table": row["table_name"],
                    "columns_count": row["columns_count"],
                    "estimated_rows": None
                    if row["estimated_rows"] is None or row["estimated_rows"] < 0
                    else int(row["estimated_rows"]),
                    "category": metadata["category"],
                    "relevance_score": metadata["relevance_score"],
                    "relevance_reason": metadata["relevance_reason"],
                    "preview_endpoint": (
                        f"/integrations/database/tables/{row['table_schema']}/{row['table_name']}/rows"
                    ),
                }
            )

        tables.sort(key=lambda item: (-item["relevance_score"], item["schema"], item["table"]))
        return tables

    def describe_table(self, schema_name: str, table_name: str) -> dict[str, Any]:
        query = """
            select
                c.column_name,
                c.data_type,
                c.is_nullable = 'YES' as nullable,
                exists (
                    select 1
                    from information_schema.table_constraints tc
                    join information_schema.key_column_usage kcu
                      on tc.constraint_name = kcu.constraint_name
                     and tc.table_schema = kcu.table_schema
                     and tc.table_name = kcu.table_name
                    where tc.constraint_type = 'PRIMARY KEY'
                      and tc.table_schema = c.table_schema
                      and tc.table_name = c.table_name
                      and kcu.column_name = c.column_name
                ) as is_primary_key,
                (
                    select ccu.table_schema || '.' || ccu.table_name || '.' || ccu.column_name
                    from information_schema.table_constraints tc
                    join information_schema.key_column_usage kcu
                      on tc.constraint_name = kcu.constraint_name
                     and tc.table_schema = kcu.table_schema
                     and tc.table_name = kcu.table_name
                    join information_schema.constraint_column_usage ccu
                      on tc.constraint_name = ccu.constraint_name
                     and tc.table_schema = ccu.table_schema
                    where tc.constraint_type = 'FOREIGN KEY'
                      and kcu.table_schema = c.table_schema
                      and kcu.table_name = c.table_name
                      and kcu.column_name = c.column_name
                    limit 1
                ) as references
            from information_schema.columns c
            where c.table_schema = %s
              and c.table_name = %s
            order by c.ordinal_position
        """

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, (schema_name, table_name))
            rows = cursor.fetchall()

        if not rows:
            raise RemoteDatabaseError(
                f"Tabela não encontrada no PostgreSQL remoto: {schema_name}.{table_name}"
            )

        columns = [row["column_name"] for row in rows]
        metadata = _table_metadata(table_name, columns)
        tables = self.list_tables()
        table_info = next(
            (
                table
                for table in tables
                if table["schema"] == schema_name and table["table"] == table_name
            ),
            None,
        )

        return {
            "schema": schema_name,
            "table": table_name,
            "columns_count": len(rows),
            "estimated_rows": None if table_info is None else table_info["estimated_rows"],
            "category": metadata["category"],
            "relevance_score": metadata["relevance_score"],
            "relevance_reason": metadata["relevance_reason"],
            "preview_endpoint": f"/integrations/database/tables/{schema_name}/{table_name}/rows",
            "columns": [
                {
                    "name": row["column_name"],
                    "data_type": row["data_type"],
                    "nullable": row["nullable"],
                    "is_primary_key": row["is_primary_key"],
                    "references": row["references"],
                }
                for row in rows
            ],
        }

    def preview_rows(
        self,
        schema_name: str,
        table_name: str,
        limit: int = 25,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit = max(1, min(limit, settings.remote_pg_max_limit))
        offset = max(0, offset)

        self.describe_table(schema_name, table_name)

        query = sql.SQL("select * from {}.{} limit %s offset %s").format(
            sql.Identifier(schema_name),
            sql.Identifier(table_name),
        )

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, (limit, offset))
            rows = cursor.fetchall()

        return {
            "schema": schema_name,
            "table": table_name,
            "limit": limit,
            "offset": offset,
            "row_count": len(rows),
            "rows": self._sanitize_preview_rows(rows),
        }

    def fetch_room_by_id(self, room_id: str) -> dict[str, Any] | None:
        query = """
            select
                c.id,
                c.nome,
                c.tipo,
                c.area,
                c.capacidade,
                c.pavimento,
                c.predio_id,
                c.unidade_id,
                p.nome as predio_nome,
                p.campus_id,
                ca.nome as campus_nome,
                u.nome as unidade_nome
            from public.compartimento c
            left join public.predio p on p.id = c.predio_id
            left join public.campus ca on ca.nome = p.campus_id
            left join public.unidade u on u.nome = c.unidade_id
            where c.id = %s
            limit 1
        """

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, (room_id,))
            return cursor.fetchone()

    def fetch_sensor_by_external_id(self, sensor_external_id: str) -> dict[str, Any] | None:
        query = """
            select
                s.external_id,
                s.nome,
                s.tipo_nome,
                s.compartimento_id,
                c.nome as compartimento_nome
            from public.sensor s
            left join public.compartimento c on c.id = s.compartimento_id
            where s.external_id = %s
            limit 1
        """

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, (sensor_external_id,))
            return cursor.fetchone()

    def fetch_person_by_id(self, pessoa_id: str) -> dict[str, Any] | None:
        query = """
            select
                id,
                nome,
                email,
                telefone,
                matricula,
                created_at
            from public.pessoa
            where id = %s
            limit 1
        """

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, (pessoa_id,))
            return cursor.fetchone()

    def fetch_canonical_user_profile(self, pessoa_id: str) -> dict[str, Any] | None:
        """Busca o perfil mínimo sem e-mail, telefone ou senha."""
        query = """
            select
                id,
                nome,
                created_at
            from public.pessoa
            where id = %s
            limit 1
        """

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, (pessoa_id,))
            return cursor.fetchone()

    def fetch_canonical_activities(
        self,
        pessoa_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Busca atividades e metadados da missão sem dados pessoais adicionais."""
        query = """
            select
                a.id,
                a.missao_id,
                a.status,
                a.assigned_at,
                a.started_at,
                a.completed_at,
                m.tipo as mission_type,
                m.titulo as mission_title,
                m.value as mission_value
            from public.atividade a
            left join public.missao m on m.id = a.missao_id
            where a.pessoa_id = %s
            order by coalesce(a.completed_at, a.started_at, a.assigned_at) desc
            limit %s
        """

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, (pessoa_id, limit))
            return list(cursor.fetchall())

    def fetch_canonical_presence(self, room_id: str) -> dict[str, Any]:
        """Agrega presença por sala, sem retornar identificadores de pessoas."""
        query = """
            select
                count(*)::int as records_count,
                count(*) filter (where checkout_at is null)::int as occupied_count,
                max(checkin_at) filter (where checkout_at is null) as latest_open_checkin_at,
                max(coalesce(checkout_at, checkin_at)) as latest_event_at
            from public.presenca
            where compartimento_id = %s
        """

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, (room_id,))
            return cursor.fetchone() or {
                "records_count": 0,
                "occupied_count": 0,
                "latest_open_checkin_at": None,
                "latest_event_at": None,
            }

    def fetch_canonical_missions(
        self,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Lista missões remotas com limite explícito e somente leitura."""
        query = """
            select
                id,
                tipo,
                titulo,
                descricao,
                value,
                ativo,
                parent_id,
                created_at
            from public.missao
            where (%s = false or ativo = true)
            order by created_at desc, id
            limit %s
        """

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, (active_only, limit))
            return list(cursor.fetchall())

    def fetch_canonical_parameter_definitions(
        self,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Lista definições de parâmetros sem valores de usuário ou telemetria."""
        query = """
            select
                id,
                data_type,
                numeric_unit,
                tipo_nome,
                nome,
                descricao,
                ativo
            from public.parametro_def
            where (%s = false or ativo = true)
            order by tipo_nome, nome, id
            limit %s
        """

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, (active_only, limit))
            return list(cursor.fetchall())

    def fetch_latest_sensor_measurement(self, sensor_external_id: str) -> dict[str, Any] | None:
        """Última medição de um sensor, no formato usado pelo contexto proativo."""
        return self._fetch_latest_measurement(
            """
                select m2.id
                from public.medicao m2
                where m2.sensor_external_id = %s
                order by m2.timestamp desc
                limit 1
            """,
            sensor_external_id,
        )

    def fetch_latest_room_measurement(self, room_id: str) -> dict[str, Any] | None:
        """Última medição registrada entre os sensores de um compartimento."""
        return self._fetch_latest_measurement(
            """
                select m2.id
                from public.medicao m2
                join public.sensor s2 on s2.external_id = m2.sensor_external_id
                where s2.compartimento_id = %s
                order by m2.timestamp desc
                limit 1
            """,
            room_id,
        )

    def _fetch_latest_measurement(
        self,
        latest_id_query: str,
        param: str,
    ) -> dict[str, Any] | None:
        """Monta o payload de medição (mesmo formato da API Spring) a partir do PostgreSQL."""
        query = f"""
            select
                m.id,
                m.timestamp,
                m.source,
                m.sensor_external_id,
                s.compartimento_id,
                pd.nome as metric,
                pd.numeric_unit as unit,
                pv.numeric_value,
                pv.boolean_value,
                pv.text_value
            from public.medicao m
            join public.parametro_valor pv on pv.medicao_id = m.id
            join public.parametro_def pd on pd.id = pv.parametro_def_id
            left join public.sensor s on s.external_id = m.sensor_external_id
            where m.id = ({latest_id_query})
        """

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, (param,))
            rows = cursor.fetchall()

        if not rows:
            return None

        valores: dict[str, Any] = {}
        unidades: dict[str, str | None] = {}
        for row in rows:
            value = row["numeric_value"]
            if value is None:
                value = row["boolean_value"]
            if value is None:
                value = row["text_value"]
            if isinstance(value, Decimal):
                value = float(value)
            valores[row["metric"]] = value
            unidades[row["metric"]] = row["unit"]

        first = rows[0]
        timestamp = first["timestamp"]
        return {
            "id": str(first["id"]),
            "timestamp": (
                timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)
            ),
            "source": first["source"] or "postgresql",
            "sensorExternalId": first["sensor_external_id"],
            "compartimentoId": first["compartimento_id"],
            "valores": valores,
            "unidades": unidades,
        }

    def search_rooms(self, query_text: str = "", limit: int = 20) -> list[dict[str, Any]]:
        pattern = f"%{query_text.strip()}%"
        query = """
            select
                c.id,
                c.nome,
                c.tipo,
                c.predio_id,
                c.unidade_id,
                p.nome as predio_nome,
                ca.nome as campus_nome
            from public.compartimento c
            left join public.predio p on p.id = c.predio_id
            left join public.campus ca on ca.nome = p.campus_id
            where (
                %s = ''
                or c.id ilike %s
                or c.nome ilike %s
                or coalesce(c.tipo, '') ilike %s
                or coalesce(p.nome, '') ilike %s
                or coalesce(ca.nome, '') ilike %s
            )
            order by c.nome, c.id
            limit %s
        """

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                query,
                (
                    query_text.strip(),
                    pattern,
                    pattern,
                    pattern,
                    pattern,
                    pattern,
                    limit,
                ),
            )
            rows = cursor.fetchall()

        options: list[dict[str, Any]] = []
        for row in rows:
            description_parts = [
                part
                for part in [row.get("predio_nome"), row.get("tipo"), row.get("campus_nome")]
                if part
            ]
            options.append(
                {
                    "id": row["id"],
                    "label": row["nome"],
                    "description": " | ".join(description_parts) if description_parts else None,
                    "metadata": {
                        "predio_id": row.get("predio_id"),
                        "unidade_id": row.get("unidade_id"),
                    },
                }
            )
        return options

    def search_sensors(
        self,
        query_text: str = "",
        room_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        pattern = f"%{query_text.strip()}%"
        room_filter = room_id or ""
        query = """
            select
                s.external_id,
                s.nome,
                s.tipo_nome,
                s.compartimento_id,
                c.nome as compartimento_nome
            from public.sensor s
            left join public.compartimento c on c.id = s.compartimento_id
            where (
                %s = ''
                or s.external_id ilike %s
                or s.nome ilike %s
                or coalesce(s.tipo_nome, '') ilike %s
                or coalesce(c.nome, '') ilike %s
            )
              and (%s = '' or s.compartimento_id = %s)
            order by s.nome, s.external_id
            limit %s
        """

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                query,
                (
                    query_text.strip(),
                    pattern,
                    pattern,
                    pattern,
                    pattern,
                    room_filter,
                    room_filter,
                    limit,
                ),
            )
            rows = cursor.fetchall()

        options: list[dict[str, Any]] = []
        for row in rows:
            description_parts = [
                part
                for part in [row.get("nome"), row.get("tipo_nome"), row.get("compartimento_nome")]
                if part
            ]
            options.append(
                {
                    "id": row["external_id"],
                    "label": row["nome"] or row["external_id"],
                    "description": " | ".join(description_parts) if description_parts else None,
                    "metadata": {
                        "room_id": row.get("compartimento_id"),
                        "tipo_nome": row.get("tipo_nome"),
                    },
                }
            )
        return options

    def search_people(self, query_text: str = "", limit: int = 20) -> list[dict[str, Any]]:
        pattern = f"%{query_text.strip()}%"
        query = """
            select
                id,
                nome
            from public.pessoa
            where (
                %s = ''
                or id ilike %s
                or nome ilike %s
            )
            order by nome, id
            limit %s
        """

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                query,
                (
                    query_text.strip(),
                    pattern,
                    pattern,
                    limit,
                ),
            )
            rows = cursor.fetchall()

        options: list[dict[str, Any]] = []
        for row in rows:
            options.append(
                {
                    "id": row["id"],
                    "label": row["nome"],
                    "description": None,
                    "metadata": {},
                }
            )
        return options


class SpringApiCatalogService:
    """Lista e invoca endpoints da API Spring Boot remota."""

    def __init__(self) -> None:
        self._endpoints = {endpoint.id: endpoint for endpoint in SPRING_ENDPOINTS}
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def get_connection_info(self) -> dict[str, Any]:
        return {
            "base_url": settings.remote_spring_base_url.rstrip("/"),
            "timeout_seconds": settings.remote_spring_timeout_seconds,
            "auth_configured": self._auth_enabled(),
        }

    def _auth_enabled(self) -> bool:
        return bool(settings.remote_spring_username and settings.remote_spring_password)

    @staticmethod
    def _decode_token_expiry(token: str) -> float:
        """Extrai o exp do JWT (sem validar assinatura) com margem de segurança."""
        try:
            payload = token.split(".")[1]
            padded = payload + "=" * (-len(payload) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded))
            return float(data.get("exp", 0)) - 60
        except Exception:
            return time.time() + 300

    def _login(self) -> str:
        """Autentica em /api/auth/login e cacheia o accessToken JWT."""
        url = f"{settings.remote_spring_base_url.rstrip('/')}/api/auth/login"
        timeout = httpx.Timeout(settings.remote_spring_timeout_seconds)
        credentials = {
            "email": settings.remote_spring_username,
            "password": settings.remote_spring_password,
        }

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, json=credentials)
        except Exception as exc:
            raise RemoteSpringApiError(
                f"Falha ao autenticar na API Spring Boot: {exc}"
            ) from exc

        if response.status_code != 200:
            raise RemoteSpringApiError(
                f"Login na API Spring Boot recusado (status {response.status_code}). "
                "Verifique REMOTE_SPRING_USERNAME e REMOTE_SPRING_PASSWORD."
            )

        try:
            token = response.json().get("accessToken")
        except ValueError:
            token = None
        if not token:
            raise RemoteSpringApiError(
                "API Spring Boot não retornou accessToken no login."
            )

        self._token = token
        self._token_expires_at = self._decode_token_expiry(token)
        return token

    def _get_token(self, force_refresh: bool = False) -> str:
        if force_refresh or not self._token or time.time() >= self._token_expires_at:
            return self._login()
        return self._token

    def list_endpoints(self) -> list[dict[str, Any]]:
        endpoints = [asdict(endpoint) for endpoint in self._endpoints.values()]
        endpoints.sort(key=lambda item: (-item["relevance_score"], item["category"], item["id"]))
        return endpoints

    def invoke_endpoint(
        self,
        endpoint_id: str,
        path_params: dict[str, str] | None = None,
        query_params: dict[str, Any] | None = None,
        body: dict[str, Any] | list[Any] | None = None,
    ) -> dict[str, Any]:
        endpoint = self._endpoints.get(endpoint_id)
        if endpoint is None:
            raise EndpointNotFoundError(f"Endpoint '{endpoint_id}' não existe no catálogo.")

        if not endpoint.invoke_supported:
            raise EndpointInvocationNotSupportedError(
                f"Endpoint '{endpoint_id}' foi observado, mas ainda não tem path completo confirmado."
            )

        path_params = path_params or {}
        query_params = query_params or {}

        try:
            path = endpoint.path_template.format(**path_params)
        except KeyError as exc:
            raise EndpointInvocationNotSupportedError(
                f"Parâmetro de path ausente para '{endpoint_id}': {exc.args[0]}"
            ) from exc

        url = f"{settings.remote_spring_base_url.rstrip('/')}{path}"
        timeout = httpx.Timeout(settings.remote_spring_timeout_seconds)

        headers: dict[str, str] = {}
        if self._auth_enabled():
            headers["Authorization"] = f"Bearer {self._get_token()}"

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.request(
                    endpoint.method,
                    url,
                    params=query_params or None,
                    json=body,
                    headers=headers or None,
                )
                if response.status_code == 401 and self._auth_enabled():
                    headers["Authorization"] = f"Bearer {self._get_token(force_refresh=True)}"
                    response = client.request(
                        endpoint.method,
                        url,
                        params=query_params or None,
                        json=body,
                        headers=headers,
                    )
        except Exception as exc:
            raise RemoteSpringApiError(
                f"Falha ao invocar o endpoint remoto '{endpoint_id}': {exc}"
            ) from exc

        content_type = response.headers.get("content-type", "")
        payload: Any
        if "application/json" in content_type:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text
        else:
            payload = response.text

        return {
            "endpoint_id": endpoint.id,
            "method": endpoint.method,
            "path_template": endpoint.path_template,
            "final_url": str(response.request.url),
            "status_code": response.status_code,
            "content_type": content_type,
            "data": payload,
        }


_remote_postgres_catalog_service: RemotePostgresCatalogService | None = None
_spring_api_catalog_service: SpringApiCatalogService | None = None


def get_remote_postgres_catalog_service() -> RemotePostgresCatalogService:
    global _remote_postgres_catalog_service
    if _remote_postgres_catalog_service is None:
        _remote_postgres_catalog_service = RemotePostgresCatalogService()
    return _remote_postgres_catalog_service


def get_spring_api_catalog_service() -> SpringApiCatalogService:
    global _spring_api_catalog_service
    if _spring_api_catalog_service is None:
        _spring_api_catalog_service = SpringApiCatalogService()
    return _spring_api_catalog_service
