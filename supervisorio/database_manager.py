import os
import json
import math
import tempfile
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QInputDialog, QLineEdit, QFormLayout
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

class AddMaterialDialog(QDialog):
    """
    Diálogo para inserção manual de um novo padrão espectral (Slate Dark Minimalist).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cadastrar Novo Padrão Espectral")
        self.setFixedSize(400, 380)
        self.setStyleSheet("""
            QDialog {
                background-color: #1E293B;
                color: #F8FAFC;
                font-family: 'Segoe UI';
            }
            QLabel {
                color: #94A3B8;
                font-size: 11px;
                font-weight: bold;
            }
            QLineEdit {
                background-color: #0F172A;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #F8FAFC;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: bold;
            }
            QLineEdit:focus {
                border: 1px solid #06B6D4;
            }
            QPushButton {
                background-color: #06B6D4;
                color: #FFFFFF;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #0891B2;
            }
            QPushButton#btnCancel {
                background-color: #334155;
                color: #E2E8F0;
            }
            QPushButton#btnCancel:hover {
                background-color: #475569;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("NOVA ASSINATURA ESPECTRAL (6-CANIAIS)")
        title.setStyleSheet("color: #F8FAFC; font-size: 13px; font-weight: bold; margin-bottom: 8px;")
        layout.addWidget(title)

        form = QFormLayout()
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Ex: Polietileno de Baixa Densidade (LDPE)")
        form.addRow("Nome do Material:", self.txt_name)

        self.wl_inputs = []
        labels = ["610nm (Vermelho):", "680nm (Vermelho Prof.):", "730nm (NIR 730):", "760nm (NIR 760):", "810nm (NIR 810):", "860nm (NIR 860):"]
        for lbl in labels:
            txt = QLineEdit()
            txt.setPlaceholderText("0.0 - 100.0")
            form.addRow(lbl, txt)
            self.wl_inputs.append(txt)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setObjectName("btnCancel")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("Salvar Padrão")
        btn_save.clicked.connect(self.on_save)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)

        self.material_data = None

    def on_save(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Aviso", "Por favor, digite o nome do material.")
            return

        values = []
        for inp in self.wl_inputs:
            try:
                v = float(inp.text().replace(',', '.'))
                if not math.isfinite(v) or v < 0:
                    raise ValueError("Valor não finito ou negativo")
                values.append(v)
            except ValueError:
                QMessageBox.warning(self, "Erro", "Preencha todos os 6 canais com valores numéricos válidos.")
                return

        self.material_data = (name, values)
        self.accept()

class DatabaseManagerDialog(QDialog):
    """
    Gerenciador de Banco de Dados Espectrais JSON com tabela, edição e exclusão (Slate Dark Modern).
    """
    def __init__(self, json_path, parent=None):
        super().__init__(parent)
        self.json_path = json_path
        self.setWindowTitle("Gerenciador de Banco de Dados de Assinaturas Espectrais NIR (GY-AS7263)")
        self.resize(800, 500)
        self.setStyleSheet("""
            QDialog {
                background-color: #1E293B;
                color: #F8FAFC;
                font-family: 'Segoe UI';
            }
            QLabel#lblTitle {
                color: #F8FAFC;
                font-size: 15px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            QTableWidget {
                background-color: #0F172A;
                border: 1px solid #334155;
                border-radius: 8px;
                gridline-color: #334155;
                color: #F8FAFC;
                selection-background-color: #06B6D4;
                selection-color: #FFFFFF;
            }
            QHeaderView::section {
                background-color: #1E293B;
                color: #94A3B8;
                font-weight: bold;
                border: 1px solid #334155;
                padding: 6px;
            }
            QPushButton {
                background-color: #06B6D4;
                color: #FFFFFF;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 14px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #0891B2;
            }
            QPushButton#btnDelete {
                background-color: #EF4444;
            }
            QPushButton#btnDelete:hover {
                background-color: #DC2626;
            }
            QPushButton#btnRename {
                background-color: #3B82F6;
            }
            QPushButton#btnRename:hover {
                background-color: #2563EB;
            }
            QPushButton#btnClose {
                background-color: #334155;
                color: #E2E8F0;
            }
            QPushButton#btnClose:hover {
                background-color: #475569;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("BANCO DE DADOS ESPECTRAIS DE REFERÊNCIA (JSON)", self)
        title.setObjectName("lblTitle")
        layout.addWidget(title)

        desc = QLabel("Gerencie os perfis espectrais de materiais conhecidos para cálculo de % Match.")
        desc.setStyleSheet("color: #94A3B8; font-size: 11px; margin-bottom: 10px;")
        layout.addWidget(desc)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Material", "610nm", "680nm", "730nm", "760nm", "810nm", "860nm"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 7):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        layout.addWidget(self.table)

        # Action Buttons Layout
        btn_layout = QHBoxLayout()

        btn_add = QPushButton("+ Adicionar Padrão Manual")
        btn_add.clicked.connect(self.add_pattern)

        btn_rename = QPushButton("Renomear Padrão")
        btn_rename.setObjectName("btnRename")
        btn_rename.clicked.connect(self.rename_pattern)

        btn_delete = QPushButton("Excluir Padrão")
        btn_delete.setObjectName("btnDelete")
        btn_delete.clicked.connect(self.delete_pattern)

        btn_close = QPushButton("Fechar")
        btn_close.setObjectName("btnClose")
        btn_close.clicked.connect(self.accept)

        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_rename)
        btn_layout.addWidget(btn_delete)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

        self.load_database()

    def load_database(self):
        self.db_data = {}
        self._database_readable = True
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict) or any(
                    not isinstance(name, str) or not isinstance(vals, list) or len(vals) != 6
                    or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v < 0 for v in vals)
                    for name, vals in loaded.items()
                ):
                    raise ValueError("O banco precisa conter seis valores finitos não negativos por material.")
                self.db_data = loaded
            except Exception as e:
                self._database_readable = False
                QMessageBox.critical(self, "Erro", f"Erro ao ler banco JSON: {str(e)}")

        self.table.setRowCount(0)
        for name, vals in self.db_data.items():
            row = self.table.rowCount()
            self.table.insertRow(row)

            item_name = QTableWidgetItem(name)
            item_name.setFont(QFont("Segoe UI", 9, QFont.Bold))
            self.table.setItem(row, 0, item_name)

            for i in range(6):
                val = vals[i] if i < len(vals) else 0.0
                item_val = QTableWidgetItem(f"{val:.1f}")
                item_val.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, i + 1, item_val)

    def save_database(self):
        temporary = None
        try:
            if not self._database_readable:
                raise ValueError("O arquivo existente não pôde ser lido. Corrija-o antes de salvar alterações.")
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=os.path.dirname(os.path.abspath(self.json_path)), delete=False) as f:
                temporary = f.name
                json.dump(self.db_data, f, indent=2, ensure_ascii=False, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, self.json_path)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao salvar arquivo JSON: {str(e)}")
            return False
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def add_pattern(self):
        dlg = AddMaterialDialog(self)
        if dlg.exec_() == QDialog.Accepted and dlg.material_data:
            name, values = dlg.material_data
            if name in self.db_data:
                QMessageBox.warning(self, "Nome existente", "Já existe um material com esse nome. Use outro nome para preservar o registro existente.")
                return
            self.db_data[name] = values
            self.save_database()
            self.load_database()

    def rename_pattern(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Selecione um material na tabela para renomear.")
            return

        old_name = self.table.item(row, 0).text()
        new_name, ok = QInputDialog.getText(
            self, "Renomear Padrão", "Novo nome para a assinatura espectral:",
            QLineEdit.Normal, old_name
        )

        if ok and new_name.strip() and new_name.strip() != old_name:
            new_name = new_name.strip()
            if new_name in self.db_data:
                QMessageBox.warning(self, "Nome existente", "Já existe um material com esse nome. Use outro nome para preservar o registro existente.")
                return
            self.db_data[new_name] = self.db_data.pop(old_name)
            self.save_database()
            self.load_database()

    def delete_pattern(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Selecione um material na tabela para excluir.")
            return

        name = self.table.item(row, 0).text()
        reply = QMessageBox.question(
            self, "Confirmar Exclusão",
            f"Tem certeza que deseja excluir o padrão '{name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if name in self.db_data:
                del self.db_data[name]
                self.save_database()
                self.load_database()
