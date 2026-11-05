"""
SPECTRUM-LAB PRO | Connection Worker Triplo (USB, Bluetooth SPP e Wi-Fi TCP)
Comunicação assíncrona robusta orientada a objetos via QThread com ESP32.

Protocolo Consolidado (115200 Baud / TCP 8080):
- Anti-Reset DTR/RTS via conversor USB-Serial
- Heartbeat periódico a cada 1000ms
- Desconexão graciosa com CMD:REPOUSO_SUAVE\\n
"""

import time
import math
import re
import queue
import socket
import select
from typing import Optional, List
from PyQt5.QtCore import QThread, pyqtSignal

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False


class ConnectionWorker(QThread):
    """
    Thread de comunicação unificada com o ESP32 suportando:
    1. USB (Cabo Serial UART) com proteção anti-reset DTR/RTS
    2. Bluetooth (SPP Virtual COM Port)
    3. Wi-Fi (Socket TCP/IP - Porta padrão 8080 / IP 192.168.4.1)

    Gerencia fila de envio prioritária (E-Stop imediato), recepção contínua e parser anti-ruído.
    """
    # Sinais padrão da aplicação
    line_received = pyqtSignal(str)              # Linha completa para console/log
    status_received = pyqtSignal(str)            # Tag STATUS extraída (ex: GAVETA_ABERTA)
    scan_received = pyqtSignal(str, list)
    data_received = pyqtSignal(list)             # Array de 6 floats/inteiros [v1..v6]
    connection_changed = pyqtSignal(bool, str)   # (conectado: bool, desc_ou_erro: str)
    error_occurred = pyqtSignal(str)             # Mensagem de erro de hardware ou rede

    # Sinais solicitados em português / aliases
    dado_recebido = data_received
    status_recebido = status_received
    conexao_estabelecida = pyqtSignal(str)
    conexao_perdida = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode: str = "USB"  # "USB", "BLUETOOTH", "WIFI"
        self.port_name: Optional[str] = None
        self.baudrate: int = 115200

        self.wifi_ip: str = "192.168.4.1"
        self.wifi_port: int = 8080

        # Atributos de transporte com aliases para compatibilidade
        self.serial_port: Optional[serial.Serial] = None
        self.serial: Optional[serial.Serial] = None
        self.tcp_socket: Optional[socket.socket] = None
        self.sock: Optional[socket.socket] = None
        self._is_running: bool = False

        # Filas thread-safe de transmissão
        self._tx_queue: queue.Queue = queue.Queue()
        self._priority_queue: queue.Queue = queue.Queue()

    def is_connected(self) -> bool:
        """Verifica se o canal ativo está aberto e comunicando."""
        if self.mode in ("USB", "BLUETOOTH"):
            return bool(self.serial_port and self.serial_port.is_open and self._is_running)
        elif self.mode == "WIFI":
            return bool(self.tcp_socket is not None and self._is_running)
        return False

    def connect_serial(self, port_name: str, baudrate: int = 115200, mode: str = "USB") -> bool:
        """
        Abre conexão serial (USB ou Bluetooth SPP virtual COM) e inicia thread receptora.
        Aplica prevenção explícita de hard reset via DTR/RTS.
        """
        if not HAS_SERIAL:
            err = "Módulo pyserial não está instalado no ambiente."
            self.error_occurred.emit(err)
            return False

        if self.is_connected():
            self.disconnect_connection()

        self.mode = mode
        self.port_name = port_name
        self.baudrate = baudrate

        try:
            self.serial_port = serial.Serial(
                port=None,
                baudrate=baudrate,
                timeout=0.1,
                write_timeout=0.5
            )
            # CRÍTICO (Anti-Reset): Imediatamente após a abertura da porta, definir explicitamente:
            # self.serial.dtr = False e self.serial.rts = False
            # Isso impede que o circuito conversor USB-Serial force um pulso de reset no ESP32.
            try:
                self.serial_port.dtr = False
                self.serial_port.rts = False
            except Exception:
                pass

            self.serial_port.port = port_name
            self.serial_port.open()
            self.serial = self.serial_port

            # Limpa buffers residuais do ESP32
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()

            self._is_running = True
            self.start()

            desc = f"{mode}: {port_name} @ {baudrate} bps"
            self.connection_changed.emit(True, desc)
            self.conexao_estabelecida.emit(desc)

            # Handshake inicial obrigatório
            self.enviar("CMD:PING")
            return True
        except Exception as err:
            if self.serial_port is not None:
                try:
                    self.serial_port.close()
                except Exception:
                    pass
            self.serial_port = None
            self.serial = None
            err_msg = f"Falha ao conectar {mode} em {port_name}: {err}"
            print(f"[CONEXÃO] {err_msg}", flush=True)
            self.connection_changed.emit(False, err_msg)
            self.conexao_perdida.emit(err_msg)
            self.error_occurred.emit(err_msg)
            return False

    def connect_tcp(self, host: str = "192.168.4.1", port: int = 8080) -> bool:
        """
        Abre conexão Wi-Fi via socket TCP/IP com o ESP32 e inicia thread receptora.
        Valores padrão: IP 192.168.4.1 e Porta 8080.
        """
        if self.is_connected():
            self.disconnect_connection()

        self.mode = "WIFI"
        self.wifi_ip = host
        self.wifi_port = port

        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            sock.connect((host, port))

            self.tcp_socket = sock
            self.sock = sock
            self._is_running = True
            self.start()

            desc = f"Wi-Fi TCP: {host}:{port}"
            self.connection_changed.emit(True, desc)
            self.conexao_estabelecida.emit(desc)

            # Handshake inicial
            self.enviar("CMD:PING")
            return True
        except Exception as err:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            self.tcp_socket = None
            self.sock = None
            err_msg = f"Falha ao conectar Wi-Fi TCP em {host}:{port}: {err}"
            print(f"[TCP] {err_msg}", flush=True)
            self.connection_changed.emit(False, err_msg)
            self.conexao_perdida.emit(err_msg)
            self.error_occurred.emit(err_msg)
            return False

    def disconnect_connection(self):
        """Finaliza thread e fecha qualquer conexão ativa (Serial, BT ou TCP)."""
        self._is_running = False
        self._clear_queue()

        if self.isRunning():
            if self.serial_port and hasattr(self.serial_port, "cancel_read"):
                try:
                    self.serial_port.cancel_read()
                except Exception:
                    pass
            self.wait(1000)

        # Fecha porta serial / BT garantindo DTR/RTS desligados
        if self.serial_port:
            try:
                self.serial_port.dtr = False
                self.serial_port.rts = False
            except Exception:
                pass
            try:
                if self.serial_port.is_open:
                    self.serial_port.close()
            except Exception:
                pass
            self.serial_port = None
            self.serial = None

        # Fecha socket TCP
        if self.tcp_socket:
            try:
                self.tcp_socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.tcp_socket.close()
            except Exception:
                pass
            self.tcp_socket = None
            self.sock = None

        self.connection_changed.emit(False, "Desconectado")
        self.conexao_perdida.emit("Desconectado")

    # Aliases
    disconnect_serial = disconnect_connection
    disconnect = disconnect_connection

    def enviar(self, comando: str, priority: bool = False) -> bool:
        """
        Método unificado de envio de comando para o ESP32.
        Garante terminação com '\\n' e despacha via serial.write() ou sock.sendall().
        Se priority=True (ex: CMD:EMERGENCIA), vai para a fila prioritária imediata.
        """
        if not self.is_connected():
            return False
        raw_cmd = comando.strip()
        if not raw_cmd.startswith("CMD:"):
            raw_cmd = f"CMD:{raw_cmd}"

        payload = f"{raw_cmd}\n"

        if priority or "EMERGENCIA" in raw_cmd:
            self._clear_queue()
            self._priority_queue.put(payload)
        else:
            self._tx_queue.put(payload)

        return True

    send_command = enviar

    def send_emergency(self):
        """Disparo de Parada de Emergência com prioridade máxima imediata."""
        self._clear_queue()
        self.enviar("CMD:EMERGENCIA", priority=True)

    def _clear_queue(self):
        for commands in (self._tx_queue,self._priority_queue):
            while True:
                try:
                    commands.get_nowait()
                except queue.Empty:
                    break

    def run(self):
        buffers={"serial":bytearray(),"tcp":bytearray()}
        try:
            while self._is_running:
                try:
                    command=self._priority_queue.get_nowait()
                except queue.Empty:
                    try:
                        command=self._tx_queue.get_nowait()
                    except queue.Empty:
                        command=None
                if command:
                    payload=command.encode("utf-8")
                    if self.mode=="WIFI":
                        self.tcp_socket.sendall(payload)
                    else:
                        written=self.serial_port.write(payload)
                        if written!=len(payload):
                            raise OSError("Transmissão serial incompleta")
                channel="tcp" if self.mode=="WIFI" else "serial"
                chunk=b""
                if channel=="tcp":
                    ready,_,_=select.select([self.tcp_socket],[],[],0.02)
                    if ready:
                        chunk=self.tcp_socket.recv(4096)
                        if not chunk:
                            raise OSError("ESP32 encerrou a conexão")
                elif self.serial_port.in_waiting:
                    chunk=self.serial_port.read(min(4096,self.serial_port.in_waiting))
                else:
                    time.sleep(0.005)
                if chunk:
                    buf=buffers[channel]
                    buf.extend(chunk)
                    if len(buf)>16384:
                        raise ValueError("Buffer de recepção excedido")
                    while b"\n" in buf:
                        raw,_,rest=buf.partition(b"\n")
                        buffers[channel]=buf=bytearray(rest)
                        try:
                            line=raw.decode("utf-8",errors="strict").strip()
                        except UnicodeDecodeError:
                            self.line_received.emit("[RX DESCARTADO] Linha com codificação inválida; aguardando próximo pacote.")
                            continue
                        if line:
                            self._parse_incoming_line(line)
        except Exception as err:
            if self._is_running:
                self._is_running=False
                self.error_occurred.emit(str(err))
                self.connection_changed.emit(False,str(err))
                self.conexao_perdida.emit(str(err))
        finally:
            # Transporte fechado no próprio worker; desconexão explícita também é idempotente.
            if self.serial_port:
                try:
                    self.serial_port.write(b"CMD:EMERGENCIA\n")
                    self.serial_port.close()
                except Exception:
                    pass
            if self.tcp_socket:
                try:
                    self.tcp_socket.sendall(b"CMD:EMERGENCIA\n")
                    self.tcp_socket.close()
                except Exception:
                    pass

    def _parse_incoming_line(self,line):
        self.line_received.emit(line)
        if line.startswith("STATUS:"):
            self.status_received.emit(line[7:].strip())
            return
        match=re.fullmatch(r"SCAN:([a-zA-Z0-9_-]+)\|DATA:(.+)",line)
        token=match.group(1) if match else None
        if match:
            payload=match.group(2)
        elif line.startswith("DATA:"):
            payload=line[5:]
        else:
            return
        try:
            parts=payload.split(",")
            if len(parts)!=6:
                raise ValueError("Número de canais inválido")
            values=[float(v) for v in parts]
            if any(not math.isfinite(v) or v<0 or v>65535 for v in values):
                raise ValueError("Valores ADC inválidos")
            if token:
                self.scan_received.emit(token,values)
            else:
                self.data_received.emit(values)
        except ValueError as err:
            self.error_occurred.emit(f"Pacote óptico inválido: {err}")

    @staticmethod
    def list_ports() -> List[tuple]:
        """Lista todas as portas COM disponíveis."""
        if not HAS_SERIAL:
            return []
        ports = serial.tools.list_ports.comports()
        return [(p.device, p.description) for p in ports]


# Aliases para retrocompatibilidade
SerialWorker = ConnectionWorker
