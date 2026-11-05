"""Native, task-oriented HMI. No scene scaling or simulated process values."""
import datetime
import time
import sqlite3
from collections import deque
from PyQt5.QtCore import Qt, QSize, QTimer, QObject, QEvent
from PyQt5.QtGui import QFont, QIcon, QPainter, QPixmap, QColor, QPainterPath, QPen
from PyQt5.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QScrollArea, QStackedWidget, QListWidget,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSizePolicy, QApplication)
from diagnostics import ControllerDiagnosticsCard
from brand_assets import institutional_signature
from version import __version__, __build__


class ResponsivePair(QWidget):
    """Reflows by available logical width, preserving font and hit-target sizes."""
    def __init__(self, first, second, breakpoint=820):
        super().__init__()
        self.items = (first, second)
        self.breakpoint = breakpoint
        self.columns = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self.reflow()

    def reflow(self):
        columns = 2 if self.width() >= self.breakpoint else 1
        if columns == self.columns:
            return
        self.columns = columns
        for item in self.items:
            self.grid.removeWidget(item)
        for i, item in enumerate(self.items):
            self.grid.addWidget(item, i // columns, i % columns)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1 if columns == 2 else 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()


class PageStack(QStackedWidget):
    def minimumSizeHint(self):
        return QSize(0, 0)

    def sizeHint(self):
        return QSize(1000, 650)


def card(title=None):
    box = QFrame()
    box.setObjectName('scadaPanel')
    box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    layout = QVBoxLayout(box)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(6)
    if title:
        caption = QLabel(title)
        caption.setObjectName('sectionTitle')
        caption.setWordWrap(True)
        layout.addWidget(caption)
    return box, layout


def note(text):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName('secondaryText')
    label.setMinimumWidth(0)
    label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    return label


def button(text, slot):
    out = QPushButton(text)
    out.setMinimumHeight(28)
    out.clicked.connect(slot)
    return out


def table(headers):
    out = QTableWidget(0, len(headers))
    out.setHorizontalHeaderLabels(headers)
    out.setEditTriggers(QAbstractItemView.NoEditTriggers)
    out.setSelectionBehavior(QAbstractItemView.SelectRows)
    out.verticalHeader().hide()
    out.verticalHeader().setDefaultSectionSize(22)
    out.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    out.horizontalHeader().setStretchLastSection(True)
    out.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    out.setMinimumWidth(0)
    out.setMinimumHeight(84)
    out.sizeHint = lambda: QSize(400, 96)
    return out


def populate(widget, rows):
    updates = widget.updatesEnabled()
    blocked = widget.blockSignals(True)
    sorting = widget.isSortingEnabled()
    widget.setUpdatesEnabled(False)
    widget.setSortingEnabled(False)
    try:
        widget.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                item = widget.item(r, c)
                text = str(value)
                if item is None:
                    widget.setItem(r, c, QTableWidgetItem(text))
                elif item.text() != text:
                    item.setText(text)
    finally:
        widget.setSortingEnabled(sorting)
        widget.blockSignals(blocked)
        widget.setUpdatesEnabled(updates)


class ResponsiveShell(QObject):
    PAGES = ('Visão geral', 'Operação', 'Espectro', 'Calibração', 'Histórico',
             'Manutenção e diagnóstico', 'Alarmes e eventos', 'Configurações')

    def __init__(self, w):
        super().__init__(w)
        self.w = w
        self.events = deque(maxlen=500)
        self._events_dirty = False
        self._last_result_key = None
        self._blink = False
        self._active_key = None
        self._table_key = None
        self._last_page = 0
        self.sensor_stale = False
        from alarm_history import AlarmHistory
        from runtime_data import data_directory
        self.alarm_storage_error = ''
        try:
            self.alarm_store = AlarmHistory(data_directory() / 'alarmes.db')
        except (OSError, sqlite3.Error) as error:
            self.alarm_store = AlarmHistory(':memory:')
            self.alarm_storage_error = f'Histórico disponível apenas nesta sessão: {error}'
        self.current_alarms = []
        self.root = QWidget()
        self.root.setObjectName('centralWidget')
        self.root.installEventFilter(self)
        w.dashboard_content = self.root
        self.layout = QVBoxLayout(self.root)
        self.layout.setContentsMargins(18, 16, 18, 12)
        self.layout.setSpacing(14)

        # Original factories own operational connections. Reparent active widgets;
        # keep hidden construction containers alive for legacy/manual aliases.
        seeds = [w._create_topbar(), w._create_kpi_bar(),
                 w._create_left_control_panel(), w._create_right_chart_panel(),
                 w._create_footer()]
        w._ui_seed_widgets = seeds
        w.kpi_bar = seeds[1]
        for seed in seeds:
            seed.setParent(self.root)
            seed.hide()
            for child in (seed, *seed.findChildren(QWidget)):
                child.setStyleSheet('')
                child._theme_base_qss = ''
                child._theme_last_qss = ''
        self.header()
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(12)
        self.nav = QListWidget()
        self.nav.setObjectName('navigation')
        self.nav.addItems(self.PAGES)
        from navigation_style import NavigationDelegate
        self.nav.setItemDelegate(NavigationDelegate(self.nav))
        self.nav.setMouseTracking(True)
        self.nav.setFixedWidth(210)
        self.nav.setFrameShape(QFrame.NoFrame)
        self.nav.setViewportMargins(0, 4, 0, 4)
        self.nav.setWordWrap(True)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.stack = PageStack()
        self.contents = []
        for name in self.PAGES:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(2, 2, 6, 2)
            page_layout.setSpacing(10)
            area = QScrollArea()
            area.setFrameShape(QFrame.NoFrame)
            area.setWidgetResizable(True)
            area.setWidget(page)
            self.stack.addWidget(area)
            self.contents.append(page_layout)
        body_layout.addWidget(self.nav)
        body_layout.addWidget(self.stack, 1)
        self.layout.addWidget(body, 1)
        self.nav.currentRowChanged.connect(self.select_page)
        self.compact_nav.currentIndexChanged.connect(self.select_page)
        self.overview()
        self.operation()
        self.spectrum()
        self.calibration()
        self.history()
        self.maintenance(seeds[0])
        self.alarms()
        self.settings()
        self.footer()
        w.setCentralWidget(self.root)
        w.control_tabs.setParent(self.root)
        w.control_tabs.hide()
        w.badge_calib.setParent(self.root)
        w.badge_calib.hide()
        w.btn_emergency_auto = w.btn_top_emergency
        w._responsive_ready = True
        self.root._scada_style_factory = self.styles
        w._scada_style_factory = self.styles
        self.nav.setCurrentRow(0)
        self.timer = QTimer(w)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(500)
        w._scada_refresh_timer = self.timer
        for widget in (w, self.root, *self.root.findChildren(QWidget)):
            w.theme_manager.apply_widget(widget)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.refresh()
        QTimer.singleShot(0, self.adapt)

    def header(self):
        from scada_ui import SpectrumMark, open_login
        w = self.w
        self.top, layout = card()
        w.topbar = self.top
        self.header_grid = QGridLayout()
        layout.addLayout(self.header_grid)
        brand = QWidget()
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        mark = SpectrumMark()
        brand_layout.addWidget(mark)
        brand_layout.addWidget(QLabel('SpectrumLAB'))
        self.header_grid.addWidget(brand, 0, 0)
        self.title = QLabel('Visão geral')
        self.title.setObjectName('pageTitle')
        self.header_grid.addWidget(self.title, 0, 1)
        self.header_grid.setColumnStretch(1, 1)
        self.user = button('Entrar', lambda: open_login(w))
        w.btn_login = self.user
        self.header_grid.addWidget(self.user, 0, 2)
        w.btn_top_emergency.setText('Parar ciclo')
        w.btn_top_emergency.setObjectName('scadaEmergency')
        w.btn_top_emergency.setMinimumWidth(110)
        w.btn_top_emergency.setToolTip('Solicita a parada ao controlador. Não substitui a emergência física.')
        self.header_grid.addWidget(w.btn_top_emergency, 0, 3)
        self.compact_nav = QComboBox()
        self.compact_nav.addItems(self.PAGES)
        self.compact_nav.hide()
        self.header_grid.addWidget(self.compact_nav, 1, 0, 1, 4)
        self.layout.addWidget(self.top)

    def overview(self):
        w = self.w
        w.card_resultado.setObjectName('scadaPanel')
        w.card_calibracao.setObjectName('scadaPanel')
        for label in w.card_calibracao.findChildren(QLabel):
            label.setWordWrap(True)
            label.setMinimumWidth(0)
        calibration_header = w.card_calibracao.layout().itemAt(0).layout()
        calibration_header.itemAt(1).widget().setText('Calibração')
        calibration_header.itemAt(1).widget().setWordWrap(False)
        w.card_calibracao.lbl_badge.setWordWrap(False)
        w.card_resultado.layout().setContentsMargins(12, 10, 12, 10)
        w.card_resultado.layout().setSpacing(4)
        w.card_calibracao.layout().setContentsMargins(12, 10, 12, 10)
        w.card_calibracao.layout().setSpacing(4)
        w.card_resultado.layout().itemAt(0).widget().setText('Número Kappa · Modelo PLS KM-SNV')
        w.lbl_kappa_valor.setObjectName('resultValue')
        for label in (w.lbl_kappa_classificacao, w.lbl_metodo_info):
            label.setWordWrap(True)
        self.result_meta = note('Nenhuma leitura concluída nesta sessão.')
        w.card_resultado.layout().addWidget(self.result_meta)
        overview_actions = QHBoxLayout()
        overview_actions.setContentsMargins(0, 0, 0, 0)
        overview_actions.setSpacing(6)
        overview_actions.addWidget(button('Nova Leitura', lambda: self.select_page(1)))
        self.reread_button = button('Reler Amostra', w.start_retained_sample_cycle)
        self.reread_button.setEnabled(False)
        overview_actions.addWidget(self.reread_button)
        w.card_resultado.layout().addLayout(overview_actions)
        self.contents[0].addWidget(ResponsivePair(w.card_resultado, w.card_calibracao, 760))
        w.spectral_chart.setMinimumHeight(165)
        self.contents[0].addWidget(w.spectral_chart, 1)

    def operation(self):
        w = self.w
        controls, layout = card('Preparar análise')
        layout.addWidget(QLabel('Método analítico'))
        layout.addWidget(w.combo_op_mode)
        w.btn_start_scan.setText('Nova Leitura')
        w.btn_start_scan.setObjectName('scadaPrimary')
        w.btn_repeatability.setText('Leitura com repetibilidade · 5×')
        layout.addWidget(w.btn_start_scan)
        layout.addWidget(w.btn_reread_sample)
        layout.addWidget(w.btn_repeatability)
        layout.addWidget(note('A identificação da amostra e as confirmações de segurança seguem o procedimento de leitura.'))
        execution, layout = card('Execução')
        w.lbl_cycle_status.setWordWrap(True)
        layout.addWidget(w.lbl_cycle_status)
        w.cycle_progress.setMinimumWidth(0)
        w.cycle_progress.setMaximumWidth(16777215)
        layout.addWidget(w.cycle_progress)
        self.complete = note('Leitura concluída. Consulte o resultado e o espectro.')
        layout.addWidget(self.complete)
        self.results_button = button('Visualizar resultados', lambda: self.select_page(0))
        self.results_button.setObjectName('scadaPrimary')
        layout.addWidget(self.results_button)
        layout.addStretch()
        self.contents[1].addWidget(ResponsivePair(controls, execution))
        self.contents[1].addStretch()

    def spectrum(self):
        from animated_chart import SpectralSplineChartWidget
        self.detail_chart = SpectralSplineChartWidget()
        self.detail_chart.setMinimumHeight(165)
        self.spectrum_meta = note('Aguardando uma leitura válida.')
        self.contents[2].addWidget(self.spectrum_meta)
        self.contents[2].addWidget(self.detail_chart, 1)
        self.channel_table = table(['Canal (nm)', 'ADC bruto', 'Escuro', 'Branco', 'Reflectância (%)'])
        self.channel_table.setFixedHeight(168)
        self.contents[2].addWidget(self.channel_table)
        w = self.w
        for item in (w.kpi_energy, w.kpi_peak, w.kpi_ratio_cel, w.kpi_ratio_water):
            if item.layout():
                item.layout().setContentsMargins(10, 6, 10, 6)
                item.layout().setSpacing(2)
            for label in item.findChildren(QLabel):
                label.setWordWrap(True)
        w.kpi_ratio_cel.lbl_title.setText('Razão R680 / R730')
        w.kpi_ratio_water.lbl_title.setText('Razão R860 / R760')
        w.kpi_bar = ResponsivePair(ResponsivePair(w.kpi_energy, w.kpi_peak, 420),
                                   ResponsivePair(w.kpi_ratio_cel, w.kpi_ratio_water, 420), 840)
        self.contents[2].addWidget(w.kpi_bar)
        self.acquisition_meta = note('Parâmetros de aquisição indisponíveis.')
        self.contents[2].addWidget(self.acquisition_meta)

    def calibration(self):
        box, layout = card('Calibração de referência')
        self.calibration_info = note('Aguardando referências.')
        layout.addWidget(self.calibration_info)
        self.w.btn_calibrate.setText('Calibrar · Branco e escuro')
        layout.addWidget(self.w.btn_calibrate)
        self.calibration_connection = button('Conectar ESP32', lambda: self.select_page(5))
        layout.addWidget(self.calibration_connection)
        self.calibration_readiness = note('Conecte o ESP32 antes de iniciar a calibração.')
        layout.addWidget(self.calibration_readiness)
        layout.addWidget(note('O procedimento mantém as confirmações, a aquisição das referências e a validação do método ativo.'))
        self.contents[3].addWidget(box)
        self.contents[3].addWidget(button('Selecionar método em Operação', lambda: self.select_page(1)))
        self.contents[3].addStretch()

    def history(self):
        # The existing history controller retains its PDF viewer, PDF generation,
        # selection and CSV code; embed the same widget rather than duplicate it.
        from main import HistoryDialog
        self.history_widget = HistoryDialog(self.w.auth_manager, self.w)
        self.history_widget.setWindowFlags(Qt.Widget)
        self.history_widget.setMinimumSize(0, 0)
        self.history_widget.btn_fechar.hide()
        self.history_widget.setStyleSheet('')
        self.history_widget.setMinimumHeight(340)
        for label in self.history_widget.findChildren(QLabel):
            label.setWordWrap(True)
            label.setMinimumWidth(0)
        self.history_actions = self.history_widget.btn_view_pdf.parentWidget().layout().itemAt(1).layout()
        for control, text in ((self.history_widget.btn_view_pdf, 'Visualizar PDF'),
                              (self.history_widget.btn_save_pdf, 'Salvar PDF'),
                              (self.history_widget.btn_export_csv, 'Exportar CSV'),
                              (self.history_widget.btn_delete, 'Excluir registro')):
            control.setText(text)
        self.contents[4].addWidget(self.history_widget, 1)

    def maintenance(self, seed):
        w = self.w
        box, layout = card('Conexão com o ESP32')
        layout.addWidget(w.combo_conn_mode)
        w.btn_refresh_ports.setText('Atualizar')
        w.btn_refresh_ports.setFixedWidth(90)
        w.btn_refresh_ports.setMinimumHeight(28)
        layout.addWidget(w.widget_serial)
        layout.addWidget(w.widget_wifi)
        layout.addWidget(w.btn_connect)
        layout.addWidget(w.badge_com)
        layout.addWidget(note('Bluetooth SPP utiliza a porta COM virtual do dispositivo pareado.'))
        self.contents[5].addWidget(box)
        w.card_esp32 = ControllerDiagnosticsCard(w)
        # Diagnostic cards use vertical key/value rows on a dedicated page.
        self.reflow_diagnostics(w.card_esp32, w.card_esp32.findChildren(QGridLayout)[0])
        self.reflow_diagnostics(w.card_telemetria, w.card_telemetria.findChildren(QGridLayout)[0])
        self.contents[5].addWidget(ResponsivePair(w.card_telemetria, w.card_esp32, 780))
        w.card_housing.setObjectName('scadaPanel')
        self.contents[5].addWidget(w.card_housing)
        manual = next(b for b in seed.findChildren(QPushButton) if 'Atuadores' in b.text())
        manual.setText('Abrir comandos manuais · Autenticação necessária')
        maint_actions = QHBoxLayout()
        maint_actions.setContentsMargins(0, 0, 0, 0)
        maint_actions.setSpacing(8)
        maint_actions.addWidget(manual)
        maint_actions.addWidget(button('Visualizar canais ADC', lambda: self.select_page(2)))
        self.contents[5].addLayout(maint_actions)
        self.contents[5].addStretch()

    @staticmethod
    def reflow_diagnostics(box, grid):
        if box.layout():
            box.layout().setContentsMargins(12, 8, 12, 8)
            box.layout().setSpacing(4)
        grid.setVerticalSpacing(4)
        grid.setHorizontalSpacing(10)
        items = []
        for r in range(grid.rowCount()):
            for c in range(grid.columnCount()):
                item = grid.itemAtPosition(r, c)
                if item and item.widget():
                    items.append(item.widget())
        for item in items:
            grid.removeWidget(item)
        pairs = [items[i:i+2] for i in range(0, len(items), 2)]
        for idx, pair in enumerate(pairs):
            row = idx // 2
            base_col = (idx % 2) * 2
            for offset, item in enumerate(pair):
                grid.addWidget(item, row, base_col + offset)
                if isinstance(item, QLabel):
                    item.setWordWrap(True)
                    item.setMinimumWidth(0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

    def alarms(self):
        self.active_table = table(['Condição', 'Estado', 'Ação orientada'])
        self.contents[6].addWidget(QLabel('Alarmes ativos e pendentes de reconhecimento'))
        self.contents[6].addWidget(self.active_table, 1)
        self.active_table.itemSelectionChanged.connect(self.update_ack_buttons)
        self.ack_selected = button('Reconhecer selecionado', lambda: self.acknowledge_alarms(False))
        self.ack_all = button('Reconhecer todos', lambda: self.acknowledge_alarms(True))
        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0,0,0,0)
        actions_layout.setSpacing(8)
        actions_layout.addWidget(self.ack_selected)
        actions_layout.addWidget(self.ack_all)
        self.contents[6].addWidget(actions)
        self.alarm_feedback = note('Reconhecer registra a ciência do operador. A causa ativa continua na lista.')
        self.contents[6].addWidget(self.alarm_feedback)
        self.contents[6].addWidget(QLabel('Histórico de alarmes · Últimas 500 ocorrências'))
        self.alarm_history_table = table(['Início', 'Condição', 'Estado', 'Reconhecido por', 'Reconhecimento', 'Fim'])
        self.contents[6].addWidget(self.alarm_history_table, 1)
        self.contents[6].addWidget(note(self.alarm_storage_error or 'Histórico salvo automaticamente. Alarmes normalizados saem da lista após o reconhecimento.'))
        self.contents[6].addWidget(QLabel('Eventos desta sessão'))
        self.event_table = table(['Horário', 'Evento'])
        self.contents[6].addWidget(self.event_table, 1)
        self.contents[6].addWidget(note('Eventos gerais: últimos 500 desta sessão. O histórico de alarmes permanece salvo ao fechar o programa.'))
        self.w.txt_console.setFixedHeight(110)
        self.w.txt_console.document().setMaximumBlockCount(1000)
        self.w.txt_console.hide()
        self.w.btn_console = QPushButton('Console de telemetria')
        self.w.btn_console.setCheckable(True)
        self.w.btn_console.toggled.connect(self.w.txt_console.setVisible)
        self.contents[6].addWidget(self.w.btn_console)
        self.contents[6].addWidget(self.w.txt_console)

    @staticmethod
    def alarm_state(row):
        return ('Ativo' if row['active'] else 'Normalizado') + (' · Reconhecido' if row['acknowledged_at'] else ' · A reconhecer')

    def update_ack_buttons(self):
        row = self.active_table.currentRow()
        self.ack_selected.setEnabled(0 <= row < len(self.current_alarms) and not self.current_alarms[row]['acknowledged_at'])
        self.ack_all.setEnabled(any(not alarm['acknowledged_at'] for alarm in self.current_alarms))

    def acknowledge_alarms(self, all_alarms=False):
        user = self.w.authenticated_user or {}
        operator = user.get('username')
        if not operator:
            self.alarm_feedback.setText('Entre com seu usuário no cabeçalho antes de reconhecer os alarmes.')
            return
        row = self.active_table.currentRow()
        alarms = self.current_alarms if all_alarms else self.current_alarms[row:row+1] if row >= 0 else []
        try:
            changed = self.alarm_store.acknowledge([alarm['id'] for alarm in alarms], operator)
        except (sqlite3.Error, OSError) as error:
            self.alarm_feedback.setText(f'Não foi possível registrar o reconhecimento: {error}')
            return
        self.alarm_feedback.setText(f'{changed} alarme(s) reconhecido(s) por {operator}. Causas ativas permanecem na lista.')
        self.w.log_message(f'[ALARMES] {changed} ocorrência(s) reconhecida(s) por {operator}.')
        self.update_alarm_views()
        self.refresh()

    def update_alarm_views(self):
        selected = self.active_table.currentRow()
        selected_id = self.current_alarms[selected]['id'] if 0 <= selected < len(self.current_alarms) else None
        self.current_alarms = self.alarm_store.current()
        self.active_table.blockSignals(True)
        populate(self.active_table, [(r['message'], self.alarm_state(r), r['action']) for r in self.current_alarms]
                 or [('Nenhum alarme ativo ou pendente', '—', '—')])
        for i, row in enumerate(self.current_alarms):
            if row['id'] == selected_id:
                self.active_table.selectRow(i)
        self.active_table.blockSignals(False)
        populate(self.alarm_history_table, [(r['raised_at'], r['message'], self.alarm_state(r),
                 r['acknowledged_by'] or '—', r['acknowledged_at'] or '—', r['cleared_at'] or '—')
                 for r in self.alarm_store.history()])
        self.update_ack_buttons()

    def settings(self):
        box, layout = card('Aparência')
        layout.addWidget(note('Escolha o tema. A preferência é salva para as próximas aberturas.'))
        self.theme_selector = QComboBox()
        for text, value in (('Claro', 'light'), ('Escuro', 'dark'), ('Seguir o sistema', 'system')):
            self.theme_selector.addItem(text, value)
        self.theme_selector.setCurrentIndex(self.theme_selector.findData(self.w.theme_manager.preference))
        self.theme_selector.currentIndexChanged.connect(self.change_theme)
        layout.addWidget(self.theme_selector)
        self.theme_feedback = note('A alteração é aplicada imediatamente.')
        layout.addWidget(self.theme_feedback)
        layout.addWidget(note('A interface acompanha a escala do Windows e reorganiza os painéis conforme a largura disponível.'))
        self.contents[7].addWidget(box)
        self.contents[7].addWidget(note(f'SpectrumLAB · Versão {__version__} · Build {__build__}'))
        self.contents[7].addStretch()
        self.w.btn_settings.clicked.disconnect()
        self.w.btn_settings.clicked.connect(lambda: self.select_page(7))

    def change_theme(self):
        ok = self.w.theme_manager.set_theme(self.theme_selector.currentData())
        self.theme_feedback.setText('Preferência salva.' if ok else 'Tema aplicado. Não foi possível salvar a preferência.')

    def footer(self):
        self.footer_box, layout = card()
        self.w.footer = self.footer_box
        self.footer_grid = QGridLayout()
        layout.addLayout(self.footer_grid)
        self.connection = button('ESP32 · Desconectado', lambda: self.select_page(5))
        self.alarm_button = button('Alarmes · 0', lambda: self.select_page(6))
        self.alarm_button.setObjectName('alarmIndicator')
        self.alarm_button.setAccessibleName('Abrir alarmes e eventos')
        self.signature = institutional_signature()
        self.footer_grid.addWidget(self.connection, 0, 0)
        self.footer_grid.addWidget(self.alarm_button, 0, 1)
        self.footer_grid.setColumnStretch(2, 1)
        self.footer_grid.addWidget(self.signature, 0, 3)
        self.layout.addWidget(self.footer_box)

    def select_page(self, index):
        if index < 0:
            return
        self.stack.setCurrentIndex(index)
        self.nav.blockSignals(True)
        self.compact_nav.blockSignals(True)
        self.nav.setCurrentRow(index)
        self.compact_nav.setCurrentIndex(index)
        self.nav.blockSignals(False)
        self.compact_nav.blockSignals(False)
        self.title.setText(self.PAGES[index])
        # One operational chart moves between pages; both views remain synchronized.
        if index == 4 and hasattr(self, 'history_widget'):
            self.history_widget._carregar_leituras(self.history_widget.txt_busca.text() or None)
        if index == 6:
            self._refresh_event_table()
        self._last_page = index
        QTimer.singleShot(0, self.adapt)

    def eventFilter(self, obj, event):
        if obj is self.root and event.type() == QEvent.Resize:
            QTimer.singleShot(0, self.adapt)
        return False

    def adapt(self):
        width = self.root.width()
        short = self.root.height() < 820
        self.layout.setContentsMargins(*( (10,6,10,6) if short else (16,12,16,10) ))
        self.layout.setSpacing(6 if short else 12)
        self.top.layout().setContentsMargins(*( (12,6,12,6) if short else (16,12,16,12) ))
        self.footer_box.layout().setContentsMargins(*( (12,5,12,5) if short else (16,10,16,10) ))
        delegate = self.nav.itemDelegate()
        dense_navigation = self.nav.height() < 580
        if delegate.compact_height != dense_navigation:
            delegate.compact_height = dense_navigation
            self.nav.doItemsLayout()
            self.nav.viewport().update()
        compact = width < 960
        self.nav.setVisible(not compact)
        self.compact_nav.setVisible(compact)
        self.title.setVisible(width >= 700)
        self.signature.setVisible(width >= 580)
        # History's existing splitter becomes vertical; no whole-page shrinking.
        from PyQt5.QtWidgets import QSplitter
        for splitter in self.history_widget.findChildren(QSplitter):
            splitter.setOrientation(Qt.Vertical if width < 1100 else Qt.Horizontal)
        from PyQt5.QtWidgets import QBoxLayout
        self.history_actions.setDirection(QBoxLayout.TopToBottom if width < 700 else QBoxLayout.LeftToRight)
        for page_layout in self.contents:
            page_layout.setSpacing(8 if short else 12)
            page_layout.activate()
        if hasattr(self, 'history_widget'):
            self.history_widget.updateGeometry()

    def record_event(self, text):
        self.events.appendleft((datetime.datetime.now().strftime('%H:%M:%S'), text))
        self._events_dirty = True

    def _refresh_event_table(self):
        if self._events_dirty and hasattr(self, 'event_table'):
            populate(self.event_table, list(self.events))
            self._events_dirty = False

    def refresh(self):
        w = self.w
        if self.stack.currentIndex() == 6:
            self._refresh_event_table()
        connected = w.is_serial_connected()
        busy = w.equipment.busy()
        self.calibration_connection.setVisible(not connected)
        self.calibration_readiness.setText(
            'Conecte o ESP32 em Manutenção e diagnóstico antes de iniciar a calibração.' if not connected
            else 'Aguardando confirmação do sensor e dos intertravamentos.' if not w.btn_calibrate.isEnabled()
            else 'Equipamento disponível para iniciar a calibração.')
        self.w.card_esp32.refresh(w)
        w.card_telemetria.refresh_freshness(busy=busy)
        mode = {'USB': 'USB', 'WIFI': 'Wi-Fi', 'BLUETOOTH': 'Bluetooth'}.get(w.combo_conn_mode.currentData(), 'USB')
        self.connection.setText(f'ESP32 · {mode} · '+('Conectado' if connected else 'Sem comunicação'))
        # A transport switch must never interrupt a mechanical/optical operation.
        for control in (w.combo_conn_mode, w.combo_com, w.txt_ip, w.txt_tcp_port, w.btn_refresh_ports, w.btn_connect):
            control.setEnabled(not busy)
        user = w.authenticated_user
        self.user.setText((str(user.get('username', 'Operador'))+' · Sair') if user else 'Entrar')
        valid_result = bool(w._result_valid)
        self.reread_button.setEnabled(w.btn_reread_sample.isEnabled())
        self.reread_button.setToolTip(w.btn_reread_sample.toolTip())
        self.results_button.setVisible(valid_result)
        self.complete.setVisible(valid_result)
        key = (bool(w._result_valid), tuple(w.current_scan_data), str(w._current_reading_timestamp),
               w.chem_engine.active_mode, w.chem_engine.calibration_id)
        if key != self._last_result_key:
            self._last_result_key = key
            valid = bool(w._result_valid)
            raw = w.current_scan_data if valid else [0.0]*6
            ref = w.current_r_calibrated if valid else [0.0]*6
            self.detail_chart.update_spectrum(raw, ref, w.current_r_snv if valid else [0.0]*6)
            snap = w._current_calibration_snapshot if valid else None
            snap = snap or {}
            white = snap.get('vetor_branco', [])
            dark = snap.get('vetor_escuro', [])
            def fmt(values, i, percent=False):
                return f'{float(values[i])*(100 if percent else 1):.2f}' if valid and len(values)>i else '—'
            populate(self.channel_table, [(nm, fmt(raw,i), fmt(dark,i), fmt(white,i), fmt(ref,i,True))
                       for i,nm in enumerate((610,680,730,760,810,860))])
            text = (f'Amostra: {w._current_sample_id or "Não informada"} · Método: {snap.get("mode", w.chem_engine.active_mode)} · '
                    f'Leitura: {w._current_reading_timestamp or "Não informado"} · Operador: {w._current_reading_operator or "Não informado"}') if valid else 'Nenhuma leitura válida disponível.'
            method = 'Seco' if w.chem_engine.active_mode == 'seco' else 'Úmido'
            self.result_meta.setText(
                f'Amostra: {w._current_sample_id or "Não informada"} · Método: {method}\n'
                f'{w._current_reading_timestamp or "Horário não informado"} · {w._current_reading_operator or "Operador não informado"}'
                if valid else text)
            self.result_meta.setToolTip(text)
            self.result_meta.setVisible(valid)
            w.lbl_metodo_info.setVisible(not valid)
            self.spectrum_meta.setText(text)
            settings = snap.get('settings', {})
            self.acquisition_meta.setText('Parâmetros registrados na aquisição: '+str(settings) if valid else 'Parâmetros de aquisição indisponíveis.')
        snap = w.chem_engine.snapshot()
        self.calibration_info.setText(('Referência válida' if w.chem_engine.calibration_valid() else 'Referência ausente ou inválida')+
            f' · Método: {w.chem_engine.active_mode}\nÚltima calibração: {snap.get("timestamp") or "Não registrada"}\n'
            f'Identificação: {w.chem_engine.calibration_id or "Não disponível"}')
        active = []
        if w.fsm_state in ('FALHA', 'EMERGENCIA') or w._emergency_lock_active:
            active.append(('controller_fault', w.lbl_cycle_status.text(), 'Verifique o equipamento e a confirmação da parada.'))
        if not w.chem_engine.calibration_valid():
            active.append(('calibration_'+w.chem_engine.active_mode, 'Calibração ausente, inválida ou expirada', 'Execute a calibração do método ativo.'))
        last = w.card_telemetria.last_received
        if not connected:
            self.sensor_stale = False
        elif last is not None:
            self.sensor_stale = time.monotonic()-last > 10 and not busy
        if connected and self.sensor_stale and not busy:
            active.append(('sensor_stale', 'Telemetria do sensor desatualizada', 'Verifique a comunicação e o sensor.'))
            w.card_telemetria.reset('Telemetria desatualizada')
        if w._sensor_ready is False and connected and w._protocol_ready:
            active.append(('sensor_unavailable', 'Sensor não disponível', 'Verifique o diagnóstico do AS7263.'))
        active_key = tuple(active)
        if active_key != self._active_key:
            try:
                self.alarm_store.synchronize(active)
                self._active_key = active_key
                self.update_alarm_views()
            except (sqlite3.Error, OSError) as error:
                self.alarm_feedback.setText(f'Falha ao salvar histórico de alarmes: {error}')
        unacknowledged = sum(not row['acknowledged_at'] for row in self.current_alarms)
        self.alarm_button.setText(f'Alarmes · {len(self.current_alarms)}')
        self.alarm_button.setToolTip(f'{len(active)} causa(s) ativa(s); {unacknowledged} ocorrência(s) aguardando reconhecimento.')
        self._blink = not self._blink
        self.alarm_button.setIcon(self.bell_icon(bool(unacknowledged) and self._blink or bool(active) and not unacknowledged))
        indicator_active = bool(active or unacknowledged)
        if self.alarm_button.property('activeAlarm') != indicator_active:
            self.alarm_button.setProperty('activeAlarm', indicator_active)
            self.alarm_button.style().unpolish(self.alarm_button)
            self.alarm_button.style().polish(self.alarm_button)
        selector_index = self.theme_selector.findData(w.theme_manager.preference)
        if self.theme_selector.currentIndex() != selector_index:
            self.theme_selector.blockSignals(True)
            self.theme_selector.setCurrentIndex(selector_index)
            self.theme_selector.blockSignals(False)

    def bell_icon(self, highlight):
        from appearance import palette_for
        p = palette_for(self.w.theme_manager.theme)
        pix = QPixmap(40, 40)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(p['warning'] if highlight else p['muted']), 2.5))
        path = QPainterPath()
        path.moveTo(9, 28)
        path.lineTo(12, 24)
        path.lineTo(12, 17)
        path.cubicTo(12, 5, 28, 5, 28, 17)
        path.lineTo(28, 24)
        path.lineTo(31, 28)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawArc(16, 27, 8, 8, 180*16, 180*16)
        painter.end()
        pix.setDevicePixelRatio(2)
        return QIcon(pix)

    def styles(self, p):
        return f'''
QWidget#centralWidget {{background:{p['canvas']};color:{p['text']};font-family:Segoe UI,Sans-Serif;font-size:12px;}}
QFrame#scadaPanel,QFrame#cardFrame {{background:{p['surface']};border:1px solid {p['border']};border-radius:7px;}}
QLabel {{color:{p['text']};font-size:12px;}}
QLabel#secondaryText {{color:{p['muted']};font-size:11px;}}
QLabel#sectionTitle {{font-size:14px;font-weight:600;}}
QLabel#pageTitle {{font-size:16px;font-weight:600;}}
QLabel#resultValue {{font-size:28px;font-weight:700;}}
QPushButton {{color:{p['text']};background:{p['surface']};border:1px solid {p['border']};border-radius:5px;padding:5px 10px;font-size:12px;}}
QPushButton:hover {{background:{p['soft']};}}
QPushButton:disabled {{color:{p['disabled']};}}
QPushButton#scadaPrimary {{background:{p['accent']};color:{'#FFFFFF' if self.w.theme_manager.theme=='light' else '#102D31'};font-weight:600;}}
QPushButton#scadaEmergency {{color:{p['danger']};border-color:{p['danger']};font-weight:600;}}
QPushButton#alarmIndicator[activeAlarm="true"] {{color:{p['warning']};border-color:{p['warning']};}}
QComboBox,QLineEdit {{background:{p['surface']};color:{p['text']};border:1px solid {p['border']};border-radius:5px;padding:5px 8px;font-size:12px;}}
QComboBox QAbstractItemView {{background:{p['surface']};color:{p['text']};selection-background-color:{p['soft']};}}
QListWidget#navigation {{background:{p['surface']};border:0;border-radius:7px;font-size:12px;}}
QScrollArea,QScrollArea>QWidget>QWidget {{background:{p['canvas']};border:0;}}
QTableWidget {{background:{p['surface']};color:{p['text']};gridline-color:{p['border']};border:0;font-size:11px;}}
QHeaderView::section {{background:{p['soft']};color:{p['text']};padding:4px 6px;border:0;font-size:11px;font-weight:600;}}
QProgressBar {{background:{p['soft']};color:{p['text']};border:0;min-height:16px;}}
QProgressBar::chunk {{background:{p['accent']};}}
QTextEdit {{background:{p['surface']};color:{p['text']};font-family:Consolas,Monospace;font-size:11px;}}
'''


def build_responsive_dashboard(window):
    window.responsive_shell = ResponsiveShell(window)
    from window_chrome import install_window_chrome
    install_window_chrome(window)
