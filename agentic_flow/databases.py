from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import create_engine, inspect, text

from .providers import CredentialCipher


DATABASE_TYPES: list[dict[str, Any]] = [
    {
        "type": "mysql",
        "node_type": "database_mysql",
        "name": "MySQL",
        "icon": "MY",
        "color": "#0ea5e9",
        "default_port": 3306,
        "driver": "mysql+pymysql",
        "description": "MySQL 5.7+ e serviços compatíveis.",
    },
    {
        "type": "postgresql",
        "node_type": "database_postgresql",
        "name": "PostgreSQL",
        "icon": "PG",
        "color": "#3b82f6",
        "default_port": 5432,
        "driver": "postgresql+psycopg",
        "description": "PostgreSQL e bancos compatíveis com seu protocolo.",
    },
    {
        "type": "sqlserver",
        "node_type": "database_sqlserver",
        "name": "SQL Server",
        "icon": "MS",
        "color": "#ef4444",
        "default_port": 1433,
        "driver": "mssql+pyodbc",
        "description": "Microsoft SQL Server via ODBC Driver 18.",
    },
    {
        "type": "sqlite",
        "node_type": "database_sqlite",
        "name": "SQLite",
        "icon": "SQ",
        "color": "#22c55e",
        "default_port": None,
        "driver": "sqlite",
        "description": "Arquivo SQLite local acessível pelo servidor.",
    },
    {
        "type": "bigquery",
        "node_type": "database_bigquery",
        "name": "Google BigQuery",
        "icon": "BQ",
        "color": "#8b5cf6",
        "default_port": None,
        "driver": "bigquery",
        "description": "Google BigQuery usando projeto, dataset e service account.",
    },
    {
        "type": "mariadb",
        "node_type": "database_mariadb",
        "name": "MariaDB",
        "icon": "MA",
        "color": "#f59e0b",
        "default_port": 3306,
        "driver": "mariadb+pymysql",
        "description": "MariaDB 10.5+ usando o driver PyMySQL.",
    },
]

DATABASE_TYPE_MAP = {item["type"]: item for item in DATABASE_TYPES}
DATABASE_NODE_TYPES = {
    item["node_type"]: item["type"] for item in DATABASE_TYPES
}

_READ_PREFIX = re.compile(
    r"^\s*(select|with|explain|show|describe|desc|pragma)\b",
    re.IGNORECASE,
)
_WRITE_TOKEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|merge|replace|"
    r"upsert|grant|revoke|call|execute|copy|attach|detach|vacuum)\b",
    re.IGNORECASE,
)
_SQL_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def validate_read_query(query: str) -> str:
    clean = query.strip()
    if clean.endswith(";"):
        clean = clean[:-1].rstrip()
    if not clean or not _READ_PREFIX.match(clean):
        raise ValueError(
            "Somente consultas de leitura (SELECT, WITH, EXPLAIN, SHOW, "
            "DESCRIBE ou PRAGMA) são permitidas."
        )
    if ";" in clean or _WRITE_TOKEN.search(clean):
        raise ValueError("A consulta contém uma operação não permitida.")
    if clean.lower().startswith("pragma") and "=" in clean:
        raise ValueError("PRAGMA de alteração não é permitido.")
    return clean


class DatabaseRuntime:
    def __init__(self, store, encryption_secret: str):
        self.store = store
        self.cipher = CredentialCipher(encryption_secret)

    def encrypt_secret(self, value: str) -> str:
        return self.cipher.encrypt(value)

    def _connection(self, connection_id: str, workspace_id: str) -> dict[str, Any]:
        connection = self.store.get_database_connection(
            connection_id, workspace_id, include_secret=True
        )
        if not connection:
            raise ValueError("A conexão de banco selecionada não existe neste workspace.")
        if not connection["enabled"]:
            raise ValueError("A conexão de banco selecionada está desativada.")
        return connection

    def _url(self, connection: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        definition = DATABASE_TYPE_MAP[connection["type"]]
        secret = self.cipher.decrypt(connection.get("secret_encrypted", ""))
        options = dict(connection.get("options") or {})
        database_type = connection["type"]
        database_name = str(connection.get("database_name") or "").strip()
        if database_type == "sqlite":
            if not database_name:
                raise ValueError("Informe o caminho do arquivo SQLite.")
            path = Path(database_name).expanduser().resolve()
            return f"sqlite:///file:{path.as_posix()}?mode=ro&uri=true", {
                "connect_args": {"check_same_thread": False}
            }
        if database_type == "bigquery":
            if not database_name:
                raise ValueError("Informe o projeto do BigQuery.")
            engine_options: dict[str, Any] = {}
            if secret:
                try:
                    service_account = json.loads(secret)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "A credencial do BigQuery precisa ser um JSON de service account."
                    ) from exc
                engine_options["credentials_info"] = service_account
            dataset = str(options.get("dataset") or "").strip()
            suffix = f"/{dataset}" if dataset else ""
            return f"bigquery://{database_name}{suffix}", engine_options
        username = quote_plus(str(connection.get("username") or ""))
        password = quote_plus(secret)
        auth = username
        if password:
            auth = f"{auth}:{password}"
        if auth:
            auth += "@"
        host = connection.get("host") or "localhost"
        port = connection.get("port") or definition.get("default_port")
        address = f"{host}:{port}" if port else str(host)
        query = ""
        if database_type == "sqlserver":
            driver = quote_plus(str(options.get("driver") or "ODBC Driver 18 for SQL Server"))
            trust = "yes" if options.get("trust_server_certificate", True) else "no"
            query = f"?driver={driver}&TrustServerCertificate={trust}"
        elif database_type in {"mysql", "mariadb"}:
            query = "?charset=utf8mb4"
        return (
            f"{definition['driver']}://{auth}{address}/{database_name}{query}",
            {},
        )

    def _engine(self, connection: dict[str, Any]):
        url, engine_options = self._url(connection)
        return create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=900,
            **engine_options,
        )

    @staticmethod
    def _serialize(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    def inspect_schema(
        self,
        *,
        connection_id: str,
        workspace_id: str,
        schema_name: str = "",
        tables: list[str] | None = None,
    ) -> dict[str, Any]:
        connection = self._connection(connection_id, workspace_id)
        engine = self._engine(connection)
        try:
            inspector = inspect(engine)
            available = inspector.get_table_names(schema=schema_name or None)
            selected = [
                name for name in available
                if not tables or name in set(tables)
            ][:100]
            result_tables = []
            for table_name in selected:
                columns = inspector.get_columns(
                    table_name, schema=schema_name or None
                )
                result_tables.append(
                    {
                        "name": table_name,
                        "columns": [
                            {
                                "name": column["name"],
                                "type": str(column["type"]),
                                "nullable": bool(column.get("nullable", True)),
                                "primary_key": bool(column.get("primary_key", False)),
                            }
                            for column in columns
                        ],
                    }
                )
            return {
                "connection": connection["name"],
                "database_type": connection["type"],
                "schema": schema_name or None,
                "tables": result_tables,
            }
        finally:
            engine.dispose()

    def execute_read_query(
        self,
        *,
        connection_id: str,
        workspace_id: str,
        query: str,
        max_rows: int = 200,
    ) -> dict[str, Any]:
        safe_query = validate_read_query(query)
        connection = self._connection(connection_id, workspace_id)
        engine = self._engine(connection)
        safe_limit = min(max(int(max_rows), 1), 1000)
        try:
            with engine.connect() as database:
                if connection["type"] in {"postgresql", "mysql", "mariadb"}:
                    database.execute(text("SET TRANSACTION READ ONLY"))
                result = database.execute(text(safe_query))
                columns = list(result.keys())
                rows = [
                    {
                        column: self._serialize(value)
                        for column, value in zip(columns, row)
                    }
                    for row in result.fetchmany(safe_limit + 1)
                ]
            truncated = len(rows) > safe_limit
            return {
                "connection": connection["name"],
                "database_type": connection["type"],
                "query": safe_query,
                "columns": columns,
                "rows": rows[:safe_limit],
                "row_count": min(len(rows), safe_limit),
                "truncated": truncated,
                "max_rows": safe_limit,
            }
        finally:
            engine.dispose()

    @staticmethod
    def _tables(config: dict[str, Any]) -> list[str]:
        return [
            item.strip()
            for item in str(config.get("tables") or "").split(",")
            if item.strip()
        ]

    def execute_node(
        self,
        *,
        config: dict[str, Any],
        workspace_id: str,
        data: dict[str, Any],
        render,
    ) -> dict[str, Any]:
        operation = str(config.get("operation") or "schema")
        query = render(str(config.get("query") or ""), data).strip()
        if operation == "query" or (operation == "auto" and query):
            return self.execute_read_query(
                connection_id=str(config.get("connection_id") or ""),
                workspace_id=workspace_id,
                query=query,
                max_rows=int(config.get("max_rows", 200)),
            )
        return self.inspect_schema(
            connection_id=str(config.get("connection_id") or ""),
            workspace_id=workspace_id,
            schema_name=str(config.get("schema_name") or ""),
            tables=self._tables(config),
        )

    def call_for_agent(
        self,
        config: dict[str, Any],
        prompt: str,
        data: dict[str, Any],
        workspace_id: str,
        render,
    ) -> dict[str, Any]:
        configured_query = render(str(config.get("query") or ""), data).strip()
        fenced = _SQL_FENCE.search(prompt)
        prompt_query = fenced.group(1).strip() if fenced else prompt.strip()
        operation = str(config.get("operation") or "auto")
        candidate = configured_query
        if not candidate and operation in {"auto", "query"} and _READ_PREFIX.match(
            prompt_query
        ):
            candidate = prompt_query
        if candidate:
            result = self.execute_read_query(
                connection_id=str(config.get("connection_id") or ""),
                workspace_id=workspace_id,
                query=candidate,
                max_rows=int(config.get("max_rows", 200)),
            )
            return {"tool": "database_read_query", "result": result}
        schema = self.inspect_schema(
            connection_id=str(config.get("connection_id") or ""),
            workspace_id=workspace_id,
            schema_name=str(config.get("schema_name") or ""),
            tables=self._tables(config),
        )
        return {"tool": "database_schema", "result": schema}

    def test_connection(
        self, connection_id: str, workspace_id: str
    ) -> dict[str, Any]:
        connection = self._connection(connection_id, workspace_id)
        engine = self._engine(connection)
        try:
            with engine.connect() as database:
                database.execute(text("SELECT 1"))
            return {
                "status": "ok",
                "database_type": connection["type"],
                "message": "Conexão estabelecida com sucesso.",
            }
        finally:
            engine.dispose()
