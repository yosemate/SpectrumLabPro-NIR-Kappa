"""
Módulo de Autenticação e Controle de Acesso (SQLite)
SPECTRUM-LAB PRO v3.1
"""

import sys
import sqlite3
import hashlib
import os
from typing import List, Dict, Optional, Tuple


def get_default_db_path() -> str:
    """Retorna caminho físico correto para usuarios.db mesmo em modo congelado (.exe)."""
    from database import get_database_path
    return get_database_path()


class AuthManager:
    """
    Gerenciador de autenticação local SQLite para o SpectrumLab Pro.
    Armazena credenciais com hash SHA-256 no arquivo usuarios.db.
    """
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path if db_path else get_default_db_path()
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        return sqlite3.connect(self.db_path)

    @staticmethod
    def hash_password(password: str) -> str:
        """Gera hash SHA-256 seguro da senha fornecida."""
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def init_db(self):
        """
        Cria a tabela de usuários se não existir e inicializa o admin padrão:
        Usuário: admin | Senha: admin | Nível: admin
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'operador'
                )
            """)
            conn.commit()

            # Verifica se a tabela está vazia
            cursor.execute("SELECT COUNT(*) FROM usuarios")
            count = cursor.fetchone()[0]
            if count == 0:
                admin_hash = self.hash_password("admin")
                cursor.execute("""
                    INSERT INTO usuarios (username, password_hash, role)
                    VALUES (?, ?, ?)
                """, ("admin", admin_hash, "admin"))
                conn.commit()

    def validar_login(self, username: str, password: str) -> bool:
        """Valida se o usuário e senha correspondem ao registro no banco."""
        user = self.obter_usuario(username)
        if not user:
            return False
        pwd_hash = self.hash_password(password)
        return user["password_hash"] == pwd_hash

    def obter_usuario(self, username: str) -> Optional[Dict]:
        """Recupera dados do usuário pelo nome de usuário."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, username, password_hash, role
                FROM usuarios
                WHERE username = ?
            """, (username,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "username": row[1],
                    "password_hash": row[2],
                    "role": row[3]
                }
        return None

    def criar_usuario(self, username: str, password: str, role: str = "operador") -> bool:
        """
        Cadastra novo usuário com senha criptografada em SHA-256.
        Retorna True se cadastrado com sucesso ou False se usuário já existir ou dados forem inválidos.
        """
        username = username.strip()
        password = password.strip()
        role = role.strip().lower()
        if not username or not password:
            return False
        if role not in ("admin", "operador"):
            role = "operador"

        pwd_hash = self.hash_password(password)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO usuarios (username, password_hash, role)
                    VALUES (?, ?, ?)
                """, (username, pwd_hash, role))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            # Username já existente
            return False
        except Exception:
            return False

    def listar_usuarios(self) -> List[Dict]:
        """Retorna a lista de todos os usuários cadastrados (sem expor senhas)."""
        usuarios = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, role FROM usuarios ORDER BY id ASC")
            for row in cursor.fetchall():
                usuarios.append({
                    "id": row[0],
                    "username": row[1],
                    "role": row[2]
                })
        return usuarios

    def contar_admins(self) -> int:
        """Conta quantos administradores existem no banco."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM usuarios WHERE role = 'admin'")
            return cursor.fetchone()[0]

    def deletar_usuario(self, username: str) -> bool:
        """
        Deleta um usuário pelo username.
        Proíbe a exclusão se for o último usuário com perfil 'admin'.
        """
        user = self.obter_usuario(username)
        if not user:
            return False

        if user["role"] == "admin":
            if self.contar_admins() <= 1:
                # Proibido excluir o último administrador
                return False

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM usuarios WHERE username = ?", (username,))
            conn.commit()
            return cursor.rowcount > 0
