import sqlite3
import os
from datetime import datetime
import logging
from pathlib import Path
import uuid

logger = logging.getLogger(__name__)

# Calcula o caminho relativo para a raiz do projeto e depois data/db
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_DIR = BASE_DIR / "data" / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = os.environ.get("SQLITE_DB_PATH", str(DB_DIR / "saved_notifications.db"))

# Valores válidos para o campo type
NOTIFICATION_TYPES = {"Pendente", "Aprovada", "Reprovada"}

def get_db_connection():
    """Retorna uma conexão com o banco de dados SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializa as tabelas do banco de dados se não existirem.

    Também aplica migrações leves (ADD COLUMN) caso a tabela já exista
    sem as colunas target_profile / prompt_used — compatível com bancos
    criados pela versão anterior do código.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saved_notifications (
                id           TEXT      PRIMARY KEY,
                type         TEXT      NOT NULL DEFAULT 'Pendente',
                content      TEXT      NOT NULL,
                persona      TEXT      NOT NULL,
                target_profile TEXT,
                prompt_used  TEXT,
                model        TEXT      NOT NULL,
                date         TEXT      NOT NULL,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Migração: adiciona colunas ausentes em bancos já existentes
        existing_columns = {
            row[1] for row in cursor.execute("PRAGMA table_info(saved_notifications)")
        }
        migrations = [
            ("target_profile", "ALTER TABLE saved_notifications ADD COLUMN target_profile TEXT"),
            ("prompt_used",    "ALTER TABLE saved_notifications ADD COLUMN prompt_used TEXT"),
        ]
        for col, ddl in migrations:
            if col not in existing_columns:
                cursor.execute(ddl)
                logger.info(f"Migração aplicada: coluna '{col}' adicionada.")

        conn.commit()
        conn.close()
        logger.info(f"Banco de dados inicializado com sucesso em: {DB_PATH}")
    except Exception as e:
        logger.error(f"Erro ao inicializar o banco de dados: {e}")


def get_all_saved_notifications():
    """Recupera todas as notificações salvas, ordenadas por data decrescente."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM saved_notifications ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "id":             row["id"],
                "type":           row["type"],
                "content":        row["content"],
                "persona":        row["persona"],
                "target_profile": row["target_profile"],
                "prompt_used":    row["prompt_used"],
                "model":          row["model"],
                "date":           row["date"],
            }
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Erro ao buscar notificações: {e}")
        return []


def save_notification(item: dict) -> bool:
    """Salva uma nova notificação no banco de dados.

    Campos esperados em *item*:
        id, type, content, persona, model, date
        target_profile  (opcional)
        prompt_used     (opcional)
    """
    try:
        notification_type = item.get("type", "Pendente")
        if notification_type not in NOTIFICATION_TYPES:
            logger.warning(f"Tipo inválido '{notification_type}'. Valores aceitos: {NOTIFICATION_TYPES}")
            return False

        new_id = item.get("id") or str(uuid.uuid4())
        new_date = item.get("date") or datetime.now().strftime("%d/%m/%Y, %H:%M:%S")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO saved_notifications
                (id, type, content, persona, target_profile, prompt_used, model, date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                new_id,
                notification_type,
                item["content"],
                item["persona"],
                item.get("target_profile"),
                item.get("prompt_used"),
                item["model"],
                new_date,
            ),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Notificação com ID {item.get('id')} já existe.")
        return False
    except Exception as e:
        logger.error(f"Erro ao salvar notificação: {e}")
        return False


def update_notification_type(notif_id: str, new_type: str) -> bool:
    """Atualiza o campo *type* de uma notificação existente.

    Valores aceitos: "Pendente", "Aprovada", "Reprovada".
    Retorna False se o ID não existir ou o tipo for inválido.
    """
    if new_type not in NOTIFICATION_TYPES:
        logger.warning(
            f"Tipo inválido '{new_type}'. Valores aceitos: {NOTIFICATION_TYPES}"
        )
        return False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE saved_notifications SET type = ? WHERE id = ?",
            (new_type, notif_id),
        )
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()
        return rows_affected > 0
    except Exception as e:
        logger.error(f"Erro ao atualizar notificação {notif_id}: {e}")
        return False


def delete_notification(notif_id: str) -> bool:
    """Deleta uma notificação pelo ID."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM saved_notifications WHERE id = ?", (notif_id,))
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()
        return rows_affected > 0
    except Exception as e:
        logger.error(f"Erro ao deletar notificação {notif_id}: {e}")
        return False


def clear_all_notifications() -> int:
    """Deleta todas as notificações. Retorna a quantidade removida."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM saved_notifications")
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()
        return rows_affected
    except Exception as e:
        logger.error(f"Erro ao limpar notificações: {e}")
        return 0
