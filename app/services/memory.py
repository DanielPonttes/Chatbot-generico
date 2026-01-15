"""
Gerenciador de memória para histórico de conversas.

Implementa armazenamento de histórico por sessão com duas opções:
- InMemoryManager: mantém em memória (perde ao reiniciar)
- SQLiteMemoryManager: persiste em banco SQLite local
"""

import logging
import sqlite3
import json
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from app.core.config import settings

logger = logging.getLogger(__name__)


class Message(TypedDict):
    """Estrutura de uma mensagem no histórico."""
    role: str  # "user" ou "assistant"
    content: str
    timestamp: str


class MemoryManager(ABC):
    """
    Interface abstrata para gerenciamento de memória de conversas.
    
    Define operações básicas para armazenar e recuperar histórico.
    """
    
    @abstractmethod
    def add_message(self, session_id: str, role: str, content: str) -> None:
        """
        Adiciona uma mensagem ao histórico da sessão.
        
        Args:
            session_id: Identificador único da sessão
            role: "user" ou "assistant"
            content: Conteúdo da mensagem
        """
        pass
    
    @abstractmethod
    def get_history(self, session_id: str, limit: int | None = None) -> list[Message]:
        """
        Recupera o histórico de mensagens de uma sessão.
        
        Args:
            session_id: Identificador da sessão
            limit: Número máximo de mensagens (None = todas)
        
        Returns:
            Lista de mensagens ordenadas cronologicamente
        """
        pass
    
    def get_formatted_history(self, session_id: str) -> list[dict]:
        """
        Retorna histórico formatado para o provider LLM.
        
        Args:
            session_id: Identificador da sessão
        
        Returns:
            Lista de dicts com {"role": "...", "content": "..."}
        """
        history = self.get_history(session_id, limit=settings.memory_max_messages)
        return [{"role": msg["role"], "content": msg["content"]} for msg in history]
    
    @abstractmethod
    def clear_session(self, session_id: str) -> None:
        """Remove todo o histórico de uma sessão."""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Libera recursos (conexões, arquivos, etc)."""
        pass


class InMemoryManager(MemoryManager):
    """
    Gerenciador de memória em RAM.
    
    - Rápido e simples
    - Perde dados ao reiniciar o servidor
    - Ideal para desenvolvimento e testes
    """
    
    def __init__(self, max_messages: int = settings.memory_max_messages):
        self._max_messages = max_messages
        self._sessions: dict[str, list[Message]] = defaultdict(list)
        logger.info(f"InMemoryManager inicializado (max_messages={max_messages})")
    
    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Adiciona mensagem e mantém apenas as últimas N."""
        message: Message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        
        self._sessions[session_id].append(message)
        
        # Mantém apenas as últimas N mensagens
        if len(self._sessions[session_id]) > self._max_messages:
            self._sessions[session_id] = self._sessions[session_id][-self._max_messages:]
    
    def get_history(self, session_id: str, limit: int | None = None) -> list[Message]:
        """Retorna histórico da sessão."""
        history = self._sessions.get(session_id, [])
        if limit is not None:
            return history[-limit:]
        return history.copy()
    
    def clear_session(self, session_id: str) -> None:
        """Limpa histórico da sessão."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.debug(f"Sessão '{session_id}' limpa")
    
    def close(self) -> None:
        """Limpa toda a memória."""
        self._sessions.clear()


class SQLiteMemoryManager(MemoryManager):
    """
    Gerenciador de memória com persistência em SQLite.
    
    - Persiste conversas entre reinicializações
    - Arquivo local, sem dependências externas
    - Ideal para produção leve
    """
    
    def __init__(
        self,
        db_path: str = settings.sqlite_path,
        max_messages: int = settings.memory_max_messages,
    ):
        self._max_messages = max_messages
        self._db_path = Path(db_path)
        
        # Cria diretório se não existir
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Conecta e cria tabela
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._create_tables()
        
        logger.info(f"SQLiteMemoryManager inicializado: {self._db_path}")
    
    def _create_tables(self) -> None:
        """Cria tabelas necessárias se não existirem."""
        cursor = self._conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_id ON messages(session_id)
        """)
        self._conn.commit()
    
    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Adiciona mensagem ao banco."""
        cursor = self._conn.cursor()
        
        # Insere nova mensagem
        cursor.execute(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (session_id, role, content, datetime.now().isoformat()),
        )
        
        # Remove mensagens antigas além do limite
        cursor.execute("""
            DELETE FROM messages 
            WHERE session_id = ? 
            AND id NOT IN (
                SELECT id FROM messages 
                WHERE session_id = ? 
                ORDER BY id DESC 
                LIMIT ?
            )
        """, (session_id, session_id, self._max_messages))
        
        self._conn.commit()
    
    def get_history(self, session_id: str, limit: int | None = None) -> list[Message]:
        """Recupera histórico do banco."""
        cursor = self._conn.cursor()
        
        if limit is not None:
            cursor.execute(
                "SELECT role, content, timestamp FROM messages "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            )
        else:
            cursor.execute(
                "SELECT role, content, timestamp FROM messages "
                "WHERE session_id = ? ORDER BY id",
                (session_id,),
            )
        
        rows = cursor.fetchall()
        
        # Se usou LIMIT, precisa inverter a ordem
        if limit is not None:
            rows = list(reversed(rows))
        
        return [
            {"role": row[0], "content": row[1], "timestamp": row[2]}
            for row in rows
        ]
    
    def clear_session(self, session_id: str) -> None:
        """Remove histórico da sessão do banco."""
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self._conn.commit()
        logger.debug(f"Sessão '{session_id}' removida do banco")
    
    def close(self) -> None:
        """Fecha conexão com o banco."""
        self._conn.close()


# ==========================================
# Factory para criar o manager correto
# ==========================================

_memory_instance: MemoryManager | None = None


def get_memory_manager() -> MemoryManager:
    """
    Factory que retorna o gerenciador de memória configurado.
    
    Usa USE_SQLITE nas configurações para decidir qual usar.
    
    Returns:
        Instância do gerenciador de memória
    """
    global _memory_instance
    
    if _memory_instance is not None:
        return _memory_instance
    
    if settings.use_sqlite:
        logger.info("Usando SQLite para persistência de conversas")
        _memory_instance = SQLiteMemoryManager()
    else:
        logger.info("Usando memória RAM (conversas não persistem)")
        _memory_instance = InMemoryManager()
    
    return _memory_instance


def close_memory_manager() -> None:
    """Fecha o gerenciador de memória e libera recursos."""
    global _memory_instance
    if _memory_instance is not None:
        _memory_instance.close()
        _memory_instance = None
