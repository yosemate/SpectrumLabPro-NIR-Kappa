"""
Diálogos de Autenticação e Gestão de Usuários
SPECTRUM-LAB PRO v3.1
"""

import os
from typing import Optional, Dict
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QFrame, QMessageBox, QAbstractItemView
)
from PyQt5.QtCore import Qt
from auth_manager import AuthManager

class DialogLogin(QDialog):
    """
    Diálogo modal de login para controle de acesso às áreas restritas do supervisório.
    """
    def __init__(self, auth_manager: Optional[AuthManager] = None, parent=None):
        super().__init__(parent)
        self.auth_manager = auth_manager or AuthManager()
        self.usuario_logado: Optional[Dict] = None

        self.setWindowTitle("🔐 Autenticação de Usuário")
        self.setFixedSize(400, 280)
        self.setModal(True)

        self.setStyleSheet("""
            QDialog {
                background-color: #202020;
                color: #FFFFFF;
                border: 1px solid #3d3d3d;
                border-radius: 8px;
            }
            QLabel {
                color: #E5E7EB;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLineEdit {
                background-color: #2b2b2b;
                color: #FFFFFF;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #0078D4;
                background-color: #333333;
            }
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #404040;
                border-color: #0078D4;
            }
            QPushButton#btnLogin {
                background-color: #0078D4;
                border: 1px solid #60CDFF;
            }
            QPushButton#btnLogin:hover {
                background-color: #0284C7;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Cabeçalho
        lbl_header = QLabel("🔐 <b>CONTROLE DE ACESSO</b>")
        lbl_header.setStyleSheet("color: #38BDF8; font-size: 14px;")
        layout.addWidget(lbl_header)

        lbl_desc = QLabel("Informe suas credenciais para acessar os controles restritos:")
        lbl_desc.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        # Campos
        self.txt_username = QLineEdit()
        self.txt_username.setPlaceholderText("Usuário")
        self.txt_username.returnPressed.connect(self._exec_login)
        layout.addWidget(self.txt_username)

        self.txt_password = QLineEdit()
        self.txt_password.setPlaceholderText("Senha")
        self.txt_password.setEchoMode(QLineEdit.Password)
        self.txt_password.returnPressed.connect(self._exec_login)
        layout.addWidget(self.txt_password)

        # Mensagem de erro
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #EF4444; font-size: 11px; font-weight: bold;")
        self.lbl_error.hide()
        layout.addWidget(self.lbl_error)

        layout.addStretch()

        # Botões
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_login = QPushButton("Entrar")
        self.btn_login.setObjectName("btnLogin")
        self.btn_login.setDefault(True)
        self.btn_login.clicked.connect(self._exec_login)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_login)
        layout.addLayout(btn_layout)

        # Foco inicial no campo de usuário
        self.txt_username.setFocus()

    def _exec_login(self):
        username = self.txt_username.text().strip()
        password = self.txt_password.text().strip()

        if not username or not password:
            self.lbl_error.setText("Preencha o usuário e a senha.")
            self.lbl_error.show()
            return

        if self.auth_manager.validar_login(username, password):
            self.usuario_logado = self.auth_manager.obter_usuario(username)
            self.lbl_error.hide()
            self.accept()
        else:
            self.lbl_error.setText("Usuário ou senha incorretos.")
            self.lbl_error.show()
            self.txt_password.selectAll()
            self.txt_password.setFocus()


class DialogGestaoUsuarios(QDialog):
    """
    Diálogo administrativo para gerenciamento de usuários, cadastro e remoção de permissões.
    """
    def __init__(self, auth_manager: Optional[AuthManager] = None, current_user: Optional[Dict] = None, parent=None):
        super().__init__(parent)
        self.auth_manager = auth_manager or AuthManager()
        self.current_user = current_user or {}

        self.setWindowTitle("👥 Gerenciamento de Usuários | SPECTRUM-LAB PRO")
        self.resize(650, 480)
        self.setModal(True)

        self.setStyleSheet("""
            QDialog {
                background-color: #202020;
                color: #FFFFFF;
                border: 1px solid #3d3d3d;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QTableWidget {
                background-color: #1a1a1a;
                color: #FFFFFF;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                gridline-color: #2d2d2d;
            }
            QHeaderView::section {
                background-color: #2b2b2b;
                color: #60CDFF;
                font-weight: bold;
                padding: 6px;
                border: 1px solid #3d3d3d;
            }
            QLineEdit, QComboBox {
                background-color: #2b2b2b;
                color: #FFFFFF;
                border: 1px solid #4a4a4a;
                border-radius: 5px;
                padding: 6px 10px;
                font-size: 11px;
            }
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
                padding: 8px 14px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #404040;
                border-color: #0078D4;
            }
            QPushButton#btnCadastrar {
                background-color: #059669;
                border: 1px solid #34D399;
            }
            QPushButton#btnCadastrar:hover {
                background-color: #047857;
            }
            QPushButton#btnExcluir {
                background-color: #7F1D1D;
                border: 1px solid #EF4444;
            }
            QPushButton#btnExcluir:hover {
                background-color: #991B1B;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Cabeçalho
        lbl_title = QLabel("👥 <b>PAINEL DE GESTÃO DE USUÁRIOS E PERMISSÕES</b>")
        lbl_title.setStyleSheet("color: #38BDF8; font-size: 13px; letter-spacing: 0.5px;")
        layout.addWidget(lbl_title)

        # Tabela de Usuários
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["ID", "Nome de Usuário", "Nível de Permissão"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table)

        # Ações na tabela
        btn_table_layout = QHBoxLayout()
        self.btn_delete = QPushButton("🗑️ Excluir Usuário Selecionado")
        self.btn_delete.setObjectName("btnExcluir")
        self.btn_delete.clicked.connect(self._delete_selected_user)
        btn_table_layout.addWidget(self.btn_delete)
        btn_table_layout.addStretch()
        layout.addLayout(btn_table_layout)

        # Formulário de Cadastro
        frame_cad = QFrame()
        frame_cad.setStyleSheet("background-color: #282828; border: 1px solid #3d3d3d; border-radius: 6px; padding: 6px;")
        cad_layout = QVBoxLayout(frame_cad)
        cad_layout.setContentsMargins(10, 8, 10, 8)
        cad_layout.setSpacing(8)

        lbl_cad_title = QLabel("<b>Cadastrar Novo Usuário</b>")
        lbl_cad_title.setStyleSheet("color: #A7F3D0; font-size: 11px;")
        cad_layout.addWidget(lbl_cad_title)

        form_layout = QHBoxLayout()
        form_layout.setSpacing(8)

        self.txt_new_username = QLineEdit()
        self.txt_new_username.setPlaceholderText("Novo Usuário")

        self.txt_new_password = QLineEdit()
        self.txt_new_password.setPlaceholderText("Nova Senha")
        self.txt_new_password.setEchoMode(QLineEdit.Password)

        self.cmb_role = QComboBox()
        self.cmb_role.addItem("Operador", "operador")
        self.cmb_role.addItem("Administrador", "admin")

        self.btn_cadastrar = QPushButton("➕ Cadastrar")
        self.btn_cadastrar.setObjectName("btnCadastrar")
        self.btn_cadastrar.clicked.connect(self._create_user)

        form_layout.addWidget(self.txt_new_username, 3)
        form_layout.addWidget(self.txt_new_password, 3)
        form_layout.addWidget(self.cmb_role, 2)
        form_layout.addWidget(self.btn_cadastrar, 2)
        cad_layout.addLayout(form_layout)

        layout.addWidget(frame_cad)

        # Botão Fechar
        bottom_layout = QHBoxLayout()
        btn_close = QPushButton("Fechar")
        btn_close.clicked.connect(self.accept)
        bottom_layout.addStretch()
        bottom_layout.addWidget(btn_close)
        layout.addLayout(bottom_layout)

        self.reload_users()

    def reload_users(self):
        """Carrega e exibe a lista de usuários do banco SQLite."""
        usuarios = self.auth_manager.listar_usuarios()
        self.table.setRowCount(len(usuarios))
        for row_idx, user in enumerate(usuarios):
            item_id = QTableWidgetItem(str(user["id"]))
            item_id.setTextAlignment(Qt.AlignCenter)
            item_user = QTableWidgetItem(user["username"])
            item_role = QTableWidgetItem(user["role"].upper())
            item_role.setTextAlignment(Qt.AlignCenter)

            if user["role"] == "admin":
                item_role.setForeground(Qt.yellow)

            self.table.setItem(row_idx, 0, item_id)
            self.table.setItem(row_idx, 1, item_user)
            self.table.setItem(row_idx, 2, item_role)

    def _create_user(self):
        username = self.txt_new_username.text().strip()
        password = self.txt_new_password.text().strip()
        role = self.cmb_role.currentData()

        if not username or not password:
            QMessageBox.warning(self, "Aviso", "Preencha o nome de usuário e a senha para cadastro.")
            return

        result = self.auth_manager.criar_usuario(username, password, role)
        success = result[0] if isinstance(result, tuple) else result
        if success:
            QMessageBox.information(self, "Sucesso", f"Usuário '{username}' cadastrado com sucesso!")
            self.txt_new_username.clear()
            self.txt_new_password.clear()
            self.reload_users()
        else:
            message = result[1] if isinstance(result, tuple) else f"Não foi possível cadastrar o usuário '{username}'. Verifique se o nome já existe."
            QMessageBox.critical(self, "Erro", message)

    def _delete_selected_user(self):
        selected_row = self.table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Aviso", "Selecione um usuário na tabela para excluir.")
            return

        username = self.table.item(selected_row, 1).text()

        # Impede excluir o usuário atualmente conectado
        if self.current_user and self.current_user.get("username") == username:
            QMessageBox.warning(self, "Ação Não Permitida", "Você não pode excluir o usuário atualmente em uso.")
            return

        # Confirmação
        reply = QMessageBox.question(
            self,
            "Confirmar Exclusão",
            f"Deseja realmente excluir o usuário '{username}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        if hasattr(self.auth_manager, "excluir_usuario"):
            result = self.auth_manager.excluir_usuario(username, self.current_user.get("username", ""))
        else:
            result = self.auth_manager.deletar_usuario(username)
        success = result[0] if isinstance(result, tuple) else result
        if success:
            QMessageBox.information(self, "Sucesso", f"Usuário '{username}' excluído com sucesso.")
            self.reload_users()
        else:
            QMessageBox.critical(
                self,
                "Erro na Exclusão",
                result[1] if isinstance(result, tuple) else "Não foi possível excluir o usuário. O sistema proíbe a exclusão do último administrador."
            )
