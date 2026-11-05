"""Historical PDF batch export with filters and a cancellable worker."""
import datetime
import math
import os
import re
import tempfile
from pathlib import Path

from PyQt5.QtCore import QDate, QThread, pyqtSignal
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLabel, QComboBox, QLineEdit, QDateEdit, QCheckBox, QDoubleSpinBox,
    QDialogButtonBox)
from pdf_generator import generate_pdf_report


def reading_date(value):
    text = str(value or '').strip()
    for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.datetime.fromisoformat(text).date()
    except ValueError:
        return None


def filter_readings(records, *, start=None, end=None, kappa_min=None,
                    kappa_max=None, operator='', method='', sample=''):
    result = []
    for record in records:
        day = reading_date(record.get('timestamp'))
        if (start is not None or end is not None) and day is None:
            continue
        if start is not None and day < start or end is not None and day > end:
            continue
        if operator and str(record.get('operador', '')).casefold() != operator.casefold():
            continue
        mode = 'seco' if 'sec' in str(record.get('metodo_analitico', '')).lower() else 'umido'
        if method and method != mode:
            continue
        if sample.casefold() not in str(record.get('codigo_amostra', '')).casefold():
            continue
        if kappa_min is not None or kappa_max is not None:
            try:
                value = float(record.get('kappa_estimado'))
            except (ValueError, TypeError):
                continue
            if not math.isfinite(value):
                continue
            if kappa_min is not None and value < kappa_min or kappa_max is not None and value > kappa_max:
                continue
        result.append(dict(record))
    return result


def historical_report_arguments(record):
    import json
    def stored_json(key):
        value = record.get(key)
        return json.loads(value) if isinstance(value, str) and value else value or None
    return dict(
        sample_id=record.get('codigo_amostra'), operator=record.get('operador'),
        kappa_value=record.get('kappa_estimado'),
        operational_mode='seco' if 'sec' in str(record.get('metodo_analitico', '')).lower() else 'umido',
        kappa_status=record.get('kappa_classificacao'),
        calibration_snapshot=stored_json('calibration_snapshot'),
        acquisition_count=record.get('acquisition_count') or 0,
        raw_scans=stored_json('raw_scans_json'),
        values=[record.get(f'ref_{wl}') for wl in (610, 680, 730, 760, 810, 860)],
        raw_adc_values=[record.get(f'adc_{wl}') for wl in (610, 680, 730, 760, 810, 860)],
        ratio_celulose=record.get('razao_celulose'), ratio_agua=record.get('razao_agua'),
        global_intensity_adc=record.get('intensidade_global_adc'),
        peak_wavelength_nm=record.get('pico_espectral_nm'),
        peak_intensity_adc=record.get('pico_espectral_adc'), timestamp=record.get('timestamp'))


def export_history_reports(records, directory, progress=None, cancelled=None):
    """Use a fresh folder; never replace previous exports or leave partial PDFs."""
    folder = Path(tempfile.mkdtemp(prefix='Laudos_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '_', dir=directory))
    result = {'folder': str(folder), 'files': [], 'errors': [], 'cancelled': False}
    for index, record in enumerate(records):
        if cancelled and cancelled():
            result['cancelled'] = True
            break
        name = re.sub(r'[^\w.-]+', '_', str(record.get('codigo_amostra') or 'Amostra'))[:80].strip('._') or 'Amostra'
        target = folder / f'{index+1:04d}_Relatorio_{name}.pdf'
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.pdf', dir=folder, delete=False) as stream:
                temporary = stream.name
            generate_pdf_report(temporary, **historical_report_arguments(record))
            os.replace(temporary, target)
            result['files'].append(str(target))
        except Exception as error:
            result['errors'].append(f"ID {record.get('id', '?')}: {error}")
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
        if progress:
            progress(index+1)
    return result


class PdfBatchWorker(QThread):
    progress = pyqtSignal(int)
    completed = pyqtSignal(object)

    def __init__(self, records, directory, parent=None):
        super().__init__(parent)
        self.records = records
        self.directory = directory

    def run(self):
        try:
            result = export_history_reports(self.records, self.directory,
                self.progress.emit, self.isInterruptionRequested)
        except Exception as error:
            result = {'folder': self.directory, 'files': [], 'errors': [str(error)], 'cancelled': False}
        self.completed.emit(result)


class BatchExportDialog(QDialog):
    def __init__(self, records, selected_ids, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Exportar laudos PDF em lote')
        self.setMinimumWidth(500)
        self.records = records
        self.selected_ids = set(selected_ids)
        self.filtered_records = []
        layout = QVBoxLayout(self)
        intro = QLabel('Um PDF por ensaio. Os arquivos serão salvos em uma nova subpasta.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.scope = QComboBox()
        self.scope.addItem('Todos os ensaios do histórico', 'all')
        if selected_ids:
            self.scope.addItem(f'Somente os selecionados ({len(selected_ids)})', 'selected')
            self.scope.setCurrentIndex(1)
        form.addRow('Origem:', self.scope)
        self.period = QComboBox()
        for title, value in [('Todas as datas', 'all'), ('Dia', 'day'), ('Semana (segunda a domingo)', 'week'), ('Intervalo de datas', 'range')]:
            self.period.addItem(title, value)
        form.addRow('Período:', self.period)
        dates = QHBoxLayout()
        self.start = QDateEdit(QDate.currentDate()); self.end = QDateEdit(QDate.currentDate())
        for field in (self.start, self.end):
            field.setCalendarPopup(True); field.setDisplayFormat('dd/MM/yyyy')
        dates.addWidget(self.start); dates.addWidget(QLabel('até')); dates.addWidget(self.end)
        form.addRow('Data / semana que contém:', dates)
        self.kappa_enabled = QCheckBox('Filtrar por faixa de Kappa')
        form.addRow(self.kappa_enabled)
        limits = QHBoxLayout()
        self.kappa_min = QDoubleSpinBox(); self.kappa_max = QDoubleSpinBox()
        for field in (self.kappa_min, self.kappa_max):
            field.setRange(0, 1000000); field.setDecimals(2)
        self.kappa_max.setValue(100)
        limits.addWidget(self.kappa_min); limits.addWidget(QLabel('até')); limits.addWidget(self.kappa_max)
        form.addRow('Kappa:', limits)
        self.operator = QComboBox(); self.operator.addItem('Todos', '')
        for name in sorted({str(r.get('operador') or '') for r in records} - {''}):
            self.operator.addItem(name, name)
        form.addRow('Operador:', self.operator)
        self.method = QComboBox()
        for title, value in [('Todos', ''), ('Seco', 'seco'), ('Úmido', 'umido')]: self.method.addItem(title, value)
        form.addRow('Método:', self.method)
        self.sample = QLineEdit(); self.sample.setPlaceholderText('Parte do código da amostra')
        form.addRow('Amostra:', self.sample)
        layout.addLayout(form)
        self.count = QLabel(); self.count.setWordWrap(True); layout.addWidget(self.count)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText('Escolher pasta e exportar')
        self.buttons.button(QDialogButtonBox.Cancel).setText('Cancelar')
        self.buttons.accepted.connect(self.accept); self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        for combo in (self.scope, self.period, self.operator, self.method): combo.currentIndexChanged.connect(self.update_filter)
        for date in (self.start, self.end): date.dateChanged.connect(self.update_filter)
        for spin in (self.kappa_min, self.kappa_max): spin.valueChanged.connect(self.update_filter)
        self.kappa_enabled.toggled.connect(self.update_filter); self.sample.textChanged.connect(self.update_filter)
        self.update_filter()

    def update_filter(self, *_):
        period = self.period.currentData()
        self.start.setEnabled(period != 'all'); self.end.setEnabled(period == 'range')
        enabled = self.kappa_enabled.isChecked()
        self.kappa_min.setEnabled(enabled); self.kappa_max.setEnabled(enabled)
        start = end = None
        if period != 'all':
            start = self.start.date().toPyDate(); end = start
            if period == 'week':
                start -= datetime.timedelta(days=start.weekday()); end = start + datetime.timedelta(days=6)
            elif period == 'range': end = self.end.date().toPyDate()
        invalid = (start is not None and start > end) or (enabled and self.kappa_min.value() > self.kappa_max.value())
        records = self.records if self.scope.currentData() == 'all' else [r for r in self.records if r.get('id') in self.selected_ids]
        self.filtered_records = [] if invalid else filter_readings(records, start=start, end=end,
            kappa_min=self.kappa_min.value() if enabled else None, kappa_max=self.kappa_max.value() if enabled else None,
            operator=self.operator.currentData(), method=self.method.currentData(), sample=self.sample.text().strip())
        text = 'Corrija o intervalo: o início precisa ser menor ou igual ao fim.' if invalid else f'{len(self.filtered_records)} ensaio(s) serão exportados.'
        if start is not None and not invalid: text += f' Período: {start:%d/%m/%Y} a {end:%d/%m/%Y}.'
        self.count.setText(text)
        self.buttons.button(QDialogButtonBox.Save).setEnabled(bool(self.filtered_records))
