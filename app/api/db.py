import sqlite3
import os
import json
from datetime import datetime
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Calcula o caminho relativo para a raiz do projeto e depois data/db
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_DIR = BASE_DIR / "data" / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = os.environ.get("SQLITE_DB_PATH", str(DB_DIR / "saved_notifications.db"))

def get_db_connection():
    """Retorna uma conexão com o banco de dados SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializa as tabelas do banco de dados se não existirem."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Tabela para as notificações salvas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saved_notifications (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                persona TEXT NOT NULL,
                model TEXT NOT NULL,
                date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info(f"Banco de dados inicializado com sucesso em: {DB_PATH}")
    except Exception as e:
        logger.error(f"Erro ao inicializar o banco de dados: {e}")

def get_all_saved_notifications():
    """Recupera todas as notificações salvas do banco, ordenadas por data descrescente."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM saved_notifications ORDER BY created_at DESC')
        rows = cursor.fetchall()
        
        notifications = []
        for row in rows:
            notifications.append({
                "id": row["id"],
                "type": row["type"],
                "content": row["content"],
                "persona": row["persona"],
                "model": row["model"],
                "date": row["date"]
            })
            
        conn.close()
        return notifications
    except Exception as e:
        logger.error(f"Erro ao buscar notificações: {e}")
        return []

def save_notification(item: dict):
    """Salva uma nova notificação no banco de dados."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO saved_notifications (id, type, content, persona, model, date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (item["id"], item["type"], item["content"], item["persona"], item["model"], item["date"]))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Notificação com ID {item.get('id')} já existe.")
        return False
    except Exception as e:
        logger.error(f"Erro ao salvar notificação: {e}")
        return False

def delete_notification(notif_id: str):
    """Deleta uma notificação pelo ID."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM saved_notifications WHERE id = ?', (notif_id,))
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()
        return rows_affected > 0
    except Exception as e:
        logger.error(f"Erro ao deletar notificação {notif_id}: {e}")
        return False

def clear_all_notifications():
    """Deleta todas as notificações."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM saved_notifications')
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()
        return rows_affected
    except Exception as e:
        logger.error(f"Erro ao limpar notificações: {e}")
        return 0
