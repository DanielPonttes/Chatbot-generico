"""
Serviços para explorar integrações externas do projeto.

Inclui:
- introspecção do PostgreSQL remoto com tabelas, colunas e amostras de dados
- catálogo da API Spring Boot com endpoints confirmados e observados no Postman
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
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
        id="setup_window_helper",
        category="setup",
        method="GET",
        path_template="Set fromIso/toIso (last 10 min...)",
        description="Request helper observado no Postman para configurar a janela temporal dos testes.",
        discovery_source="postman_screenshot",
        relevance_score=55,
        relevance_reason="Útil para testes manuais, mas não é um endpoint de domínio confirmado.",
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
        path_template="/api/sensors/seed/from-...",
        description="Bootstrap de sensores a partir da base legada; visível no Postman, mas sem path completo confirmado.",
        discovery_source="postman_screenshot",
        relevance_score=84,
        relevance_reason="Relevante para povoar sensores, mas ainda exige o path exato para automação.",
        invoke_supported=False,
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
        path_template="/api/presencas/ocupacao...",
        description="Consulta de ocupação observada no Postman, mas sem o path completo visível.",
        discovery_source="postman_screenshot",
        relevance_score=90,
        relevance_reason="Muito relevante para inferir ocupação atual, porém precisa do path final para automação.",
        invoke_supported=False,
    ),
    SpringEndpointDefinition(
        id="presencas_open_observed",
        category="presencas",
        method="GET",
        path_template="/api/presencas/abertas/...",
        description="Consulta de presenças abertas observada no Postman, ainda sem path final confirmado.",
        discovery_source="postman_screenshot",
        relevance_score=90,
        relevance_reason="Muito relevante para monitorar ocupação em aberto.",
        invoke_supported=False,
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
        path_template="/api/presencas/checkout...",
        description="Segundo endpoint de checkout visível no Postman, mas sem o path completo disponível.",
        discovery_source="postman_screenshot",
        relevance_score=80,
        relevance_reason="Provavelmente útil para operações em lote ou por sala, mas ainda sem confirmação.",
        invoke_supported=False,
        side_effect=True,
    ),
)


def _table_metadata(table_name: str, columns: list[str] | None = None) -> dict[str, Any]:
    if table_name in TABLE_METADATA:
        return TABLE_METADATA[table_name]

    columns = columns or []
    lower_columns = " ".join(columns).lower()

    if "timestamp" in lower_columns or "sensor" in lower_columns:
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
            "rows": rows,
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
                nome,
                email,
                matricula
            from public.pessoa
            where (
                %s = ''
                or id ilike %s
                or nome ilike %s
                or coalesce(email, '') ilike %s
                or coalesce(matricula, '') ilike %s
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
                    pattern,
                    pattern,
                    limit,
                ),
            )
            rows = cursor.fetchall()

        options: list[dict[str, Any]] = []
        for row in rows:
            description_parts = [part for part in [row.get("matricula"), row.get("email")] if part]
            options.append(
                {
                    "id": row["id"],
                    "label": row["nome"],
                    "description": " | ".join(description_parts) if description_parts else None,
                    "metadata": {},
                }
            )
        return options


class SpringApiCatalogService:
    """Lista e invoca endpoints da API Spring Boot remota."""

    def __init__(self) -> None:
        self._endpoints = {endpoint.id: endpoint for endpoint in SPRING_ENDPOINTS}

    def get_connection_info(self) -> dict[str, Any]:
        return {
            "base_url": settings.remote_spring_base_url.rstrip("/"),
            "timeout_seconds": settings.remote_spring_timeout_seconds,
        }

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

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.request(
                    endpoint.method,
                    url,
                    params=query_params or None,
                    json=body,
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
