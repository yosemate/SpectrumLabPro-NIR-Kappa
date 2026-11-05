"""
SPECTRUM-LAB PRO | Painel Modal de Operação Manual e Manutenção de Atuadores
Implementa desacoplamento atômico de comandos manuais conforme Protocolo ESP32:
- CMD:ABRIR_GAVETA\\n   -> Aguarda STATUS:GAVETA_ABERTA
- CMD:FECHAR_GAVETA\\n  -> Aguarda STATUS:GAVETA_FECHADA
- CMD:AVANCAR_SENSOR\\n -> Aguarda STATUS:SENSOR_AVANCADO
- CMD:RECUAR_SENSOR\\n  -> Aguarda STATUS:SENSOR_RECUADO
- CMD:LER_ESPECTRO\\n   -> Aguarda STATUS:LEITURA_CONCLUIDA
- CMD:EMERGENCIA\\n     -> Aguarda STATUS:EMERGENCIA_ACIONADA
"""

import datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTextEdit, QWidget
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor


class StatusLedHelper(QWidget):
    """
    Indicador de LED visual para o Modal de Operação Manual.
    """
    def __init__(self, color_active="#06B6D4", color_inactive="#475569", parent=None):
        super().__init__(parent)
        self.color_active = color_active
        self.color_inactive = color_inactive
        self.is_active = False
        self.setFixedSize(18, 18)

    def set_active(self, active: bool):
        self.is_active = active
        self.update()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QBrush, QPen, QRadialGradient
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        color_hex = self.color_active if self.is_active else self.color_inactive
        base_color = QColor(color_hex)
        rect = self.rect()
        center = rect.center()

        if self.is_active:
            glow_grad = QRadialGradient(center.x(), center.y(), 8)
            glow_grad.setColorAt(0.0, base_color)
            glow_grad.setColorAt(0.7, base_color.lighter(130))
            glow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(glow_grad))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(rect)

        painter.setPen(QPen(base_color.lighter(140) if self.is_active else QColor("#64748B"), 1.5))
        painter.setBrush(QBrush(base_color))
        painter.drawEllipse(center, 6, 6)


class ManualControlDialog(QDialog):
    """
    Janela Modal do Painel de Operação Manual e Manutenção de Atuadores.
    Garante o desacoplamento atômico: cada botão desabilita-se até receber a confirmação de STATUS do ESP32.
    """
    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window)
        self.main_win = main_window
        self.setWindowTitle("Painel de Operação Manual e Manutenção (Bancada)")
        self.resize(680, 520)

        # Mapa de intertravamento atômico: status_esperado -> (botao, timer_watchdog)
        self._pending_buttons = {}

        self.apply_dark_style()
        self.init_ui()
        self.update_interlocks_and_leds()

    def apply_dark_style(self):
        qss = """
            QDialog {
                background-color: #0F172A;
                color: #F8FAFC;
                font-family: 'Segoe UI', Arial;
            }
            QFrame#cardFrame {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 10px;
            }
            QLabel {
                color: #F8FAFC;
            }
            QPushButton {
                background-color: #334155;
                color: #E2E8F0;
                border: 1px solid #475569;
                border-radius: 8px;
                padding: 10px 14px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #475569;
                color: #FFFFFF;
                border: 1px solid #06B6D4;
            }
            QPushButton:disabled {
                background-color: #1E293B;
                color: #64748B;
                border: 1px solid #334155;
            }
            QPushButton#btnActuator {
                background-color: #0284C7;
                color: #FFFFFF;
                border: none;
                font-size: 12px;
            }
            QPushButton#btnActuator:hover {
                background-color: #0369A1;
            }
            QPushButton#btnEmergency {
                background-color: #7F1D1D;
                color: #FCA5A5;
                border: 1px solid #EF4444;
                font-size: 12px;
            }
            QPushButton#btnEmergency:hover {
                background-color: #DC2626;
                color: #FFFFFF;
            }
            QTextEdit#miniLog {
                background-color: #0F172A;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #38BDF8;
                font-family: 'Consolas', monospace;
                font-size: 10px;
            }
        """
        self.setStyleSheet(qss)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(12)

        # 1. HEADER & LEDS BAR
        header_card = QFrame()
        header_card.setObjectName("cardFrame")
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(14, 10, 14, 10)

        title_lbl = QLabel("⚙️ CONTROLE MANUAL DE ATUADORES (BANCADA)")
        title_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #F8FAFC; letter-spacing: 0.5px;")

        header_layout.addWidget(title_lbl)
        header_layout.addStretch()

        # Status LEDs
        self.led_com = StatusLedHelper("#06B6D4", "#475569")
        lbl_com = QLabel("COM")
        lbl_com.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: bold;")

        self.led_drawer = StatusLedHelper("#10B981", "#F59E0B")
        lbl_drawer = QLabel("Gaveta")
        lbl_drawer.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: bold;")

        self.led_sensor = StatusLedHelper("#10B981", "#64748B")
        lbl_sensor = QLabel("Sensor")
        lbl_sensor.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: bold;")

        header_layout.addWidget(self.led_com)
        header_layout.addWidget(lbl_com)
        header_layout.addSpacing(8)
        header_layout.addWidget(self.led_drawer)
        header_layout.addWidget(lbl_drawer)
        header_layout.addSpacing(8)
        header_layout.addWidget(self.led_sensor)
        header_layout.addWidget(lbl_sensor)

        main_layout.addWidget(header_card)

        # 2. ACTUATOR COMMANDS PANEL (DESACOPLAMENTO ATÔMICO)
        cmd_card = QFrame()
        cmd_card.setObjectName("cardFrame")
        cmd_layout = QVBoxLayout(cmd_card)
        cmd_layout.setContentsMargins(16, 16, 16, 16)
        cmd_layout.setSpacing(10)

        lbl_sec = QLabel("COMANDOS ATÔMICOS DE ATUAÇÃO E TESTE DE BANCADA")
        lbl_sec.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        cmd_layout.addWidget(lbl_sec)

        row_door = QHBoxLayout()
        self.btn_open_door = QPushButton("Abrir Porta")
        self.btn_close_door = QPushButton("Fechar Porta")
        for button, cmd, expected, desc in (
            (self.btn_open_door, "CMD:ABRIR_PORTA", "PORTA_ABERTA", "Abrindo porta..."),
            (self.btn_close_door, "CMD:FECHAR_PORTA", "PORTA_FECHADA", "Fechando porta..."),
        ):
            button.setObjectName("btnActuator")
            button.clicked.connect(lambda checked=False, b=button, c=cmd, e=expected, d=desc:
                                   self._execute_atomic_command(b, c, e, d))
            row_door.addWidget(button)
        cmd_layout.addLayout(row_door)
        self.lbl_housing = QLabel("Carcaça: sem confirmação")
        cmd_layout.addWidget(self.lbl_housing)
        self.lbl_carriage = QLabel("Carrinho: sem confirmação")
        cmd_layout.addWidget(self.lbl_carriage)

        # Linha 1: Gaveta (Abrir / Fechar)
        row_drawer = QHBoxLayout()
        self.btn_open_drawer = QPushButton("📦 Abrir Gaveta (CMD:ABRIR_GAVETA)")
        self.btn_open_drawer.setObjectName("btnActuator")
        self.btn_open_drawer.clicked.connect(lambda: self._execute_atomic_command(
            self.btn_open_drawer, "CMD:ABRIR_GAVETA", "GAVETA_ABERTA", "Abrindo gaveta..."
        ))

        self.btn_close_drawer = QPushButton("📦 Fechar Gaveta (CMD:FECHAR_GAVETA)")
        self.btn_close_drawer.setObjectName("btnActuator")
        self.btn_close_drawer.clicked.connect(lambda: self._execute_atomic_command(
            self.btn_close_drawer, "CMD:FECHAR_GAVETA", "GAVETA_FECHADA", "Fechando gaveta..."
        ))
        row_drawer.addWidget(self.btn_open_drawer)
        row_drawer.addWidget(self.btn_close_drawer)
        cmd_layout.addLayout(row_drawer)

        # Linha 2: Sensor (Avançar / Recuar)
        row_sensor = QHBoxLayout()
        self.btn_fwd_sensor = QPushButton("🤖 Avançar Sensor (CMD:AVANCAR_SENSOR)")
        self.btn_fwd_sensor.setObjectName("btnActuator")
        self.btn_fwd_sensor.clicked.connect(lambda: self._execute_atomic_command(
            self.btn_fwd_sensor, "CMD:AVANCAR_SENSOR", "SENSOR_AVANCADO", "Avançando sensor sobre a lâmina..."
        ))

        self.btn_retract_sensor = QPushButton("🤖 Recuar Sensor (CMD:RECUAR_SENSOR)")
        self.btn_retract_sensor.setObjectName("btnActuator")
        self.btn_retract_sensor.clicked.connect(lambda: self._execute_atomic_command(
            self.btn_retract_sensor, "CMD:RECUAR_SENSOR", "SENSOR_RECUADO", "Recuando sensor para repouso..."
        ))
        row_sensor.addWidget(self.btn_fwd_sensor)
        row_sensor.addWidget(self.btn_retract_sensor)
        cmd_layout.addLayout(row_sensor)

        # Linha 3: Disparo Único e Parada de Emergência
        row_ops = QHBoxLayout()
        self.btn_single_read = QPushButton("💡 Disparo Único (CMD:LER_ESPECTRO)")
        self.btn_single_read.setObjectName("btnActuator")
        self.btn_single_read.setStyleSheet("background-color: #0284C7; font-weight: bold;")
        self.btn_single_read.clicked.connect(lambda: self._execute_atomic_command(
            self.btn_single_read, "CMD:LER_ESPECTRO", "LEITURA_CONCLUIDA", "Varredura óptica dos 6 canais..."
        ))

        self.btn_emergency = QPushButton("🛑 Parada de Emergência (CMD:EMERGENCIA)")
        self.btn_emergency.setObjectName("btnEmergency")
        self.btn_emergency.clicked.connect(self._trigger_emergency)

        row_ops.addWidget(self.btn_single_read)
        row_ops.addWidget(self.btn_emergency)
        cmd_layout.addLayout(row_ops)

        main_layout.addWidget(cmd_card)

        # 3. MINI LOG CONSOLE
        log_card = QFrame()
        log_card.setObjectName("cardFrame")
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(12, 10, 12, 10)

        lbl_log = QLabel("📋 CONSOLE DE TELEMETRIA E CONFIRMAÇÕES SERIAL")
        lbl_log.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: bold;")

        self.txt_log = QTextEdit()
        self.txt_log.setObjectName("miniLog")
        self.txt_log.setReadOnly(True)
        self.txt_log.setFixedHeight(95)

        log_layout.addWidget(lbl_log)
        log_layout.addWidget(self.txt_log)
        main_layout.addWidget(log_card)

        # Footer Close Button
        btn_close = QPushButton("Fechar Painel Manual")
        btn_close.clicked.connect(self.accept)
        main_layout.addWidget(btn_close)

        self.log("Painel de Operação Manual inicializado com protocolo atômico.")

    def log(self, msg: str):
        now_str = datetime.datetime.now().strftime("[%H:%M:%S]")
        self.txt_log.append(f"{now_str} {msg}")

    def update_interlocks_and_leds(self):
        """Atualiza indicadores visuais COM/Gaveta/Sensor."""
        hw_connected = self.main_win.is_serial_connected()
        self.led_com.set_active(hw_connected)
        equipment = self.main_win.equipment
        idle = (self.main_win.fsm_state == "IDLE" and not equipment.pending
                and not self.main_win._batch and not self.main_win._manual_pending)
        allowed = (hw_connected and equipment.manual_capable and equipment.carriage_capable and equipment.carriage_retracted is not None and equipment.housing_closed is not None
                   and self.main_win.is_manual_mode_unlocked and bool(self.main_win.authenticated_user))
        for button in (self.btn_open_door, self.btn_close_door, self.btn_open_drawer,
                       self.btn_close_drawer, self.btn_fwd_sensor, self.btn_retract_sensor):
            button.setEnabled(idle and allowed)
        chamber_closed = equipment.drawer_closed and equipment.closed and not equipment.open
        self.btn_fwd_sensor.setEnabled(idle and allowed)
        self.btn_single_read.setEnabled(idle and allowed and self.main_win._ready_for_scan() and bool(chamber_closed)
                                       and bool(equipment.carriage_advanced) and not equipment.carriage_retracted)
        self.lbl_housing.setText(self.main_win.lbl_housing_state.text())
        self.lbl_housing.setStyleSheet(self.main_win.lbl_housing_state.styleSheet())
        self.lbl_carriage.setText(self.main_win.lbl_carriage_state.text())

    def _execute_atomic_command(self,button,cmd_str,expected_status,desc):
        if self.main_win.fsm_state!="IDLE" or self.main_win._batch or self.main_win._manual_pending:
            self.log("[AVISO] Aguarde a rotina atual.")
            return
        if not self.main_win.is_serial_connected():
            self.log("[AVISO] Hardware desconectado.")
            return
        self.log("[TX] "+cmd_str+" — "+desc)
        self.main_win._execute_atomic_manual_button(button,cmd_str,expected_status,desc)

    def _on_watchdog_timeout(self,button,expected_status):
        self.main_win._fail_operation("Comando manual sem confirmação: "+expected_status)
        self.log("[FALHA] Controles bloqueados até confirmação do hardware.")

    def on_status_received(self, status_tag: str):
        """
        Chamado pelo supervisório principal quando uma telemetria STATUS:* chega do ESP32.
        """
        self.log(f"[RX STATUS] {status_tag}")

        # Atualização dos LEDs
        if status_tag == "GAVETA_ABERTA":
            self.led_drawer.set_active(False)
        elif status_tag == "GAVETA_FECHADA":
            self.led_drawer.set_active(True)
        elif status_tag == "SENSOR_AVANCADO":
            self.led_sensor.set_active(True)
        elif status_tag == "SENSOR_RECUADO":
            self.led_sensor.set_active(False)

        # Liberação atômica do botão associado ao status
        if status_tag in self._pending_buttons:
            button, watchdog = self._pending_buttons.pop(status_tag)
            try:
                watchdog.stop()
            except Exception:
                pass
            button.setEnabled(True)
            self.log(f"[OK] Ação confirmada: STATUS:{status_tag}. Controle liberado.")

        if status_tag == "EMERGENCIA_ACIONADA":
            # Reabilita todos os botões caso estivessem pendentes
            for status, (btn, timer) in list(self._pending_buttons.items()):
                try:
                    timer.stop()
                except Exception:
                    pass
                btn.setEnabled(True)
            self._pending_buttons.clear()
            self.log("[EMERGENCIA] Hardware em estado seguro.")

    def _trigger_emergency(self):
        """Dispara parada de emergência prioritária."""
        self.log("[EMERGENCIA] Acionando CMD:EMERGENCIA imediatamente!")
        self.main_win.stop_cycle_action()
