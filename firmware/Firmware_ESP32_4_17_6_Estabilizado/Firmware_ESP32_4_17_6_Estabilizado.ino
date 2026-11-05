#include <Wire.h>
#include "src/Adafruit_AS726x.h"
#include <ESP32Servo.h>
#include <WiFi.h>
#include "BluetoothSerial.h"

// SpectrumLabPro / PLS_ACQ_1 (Revisao Estabilizada 4.17.6):
// 1. Pre-aquecimento automatico do LED quando frio (>1500 ms desligado) para eliminar rampa termica nos disparos 1-3.
// 2. Dupla integracao interna (2x oversampling por leitura) mantendo a mesma escala ADC [0..65535] e protocolo PLS_ACQ_1.
// 3. Desligamento de PWM (detach) de servoPorta e servoCarrinho quando parados, eliminando microvibracao e ruido eletrico durante a leitura optica.
BluetoothSerial SerialBT;
WiFiServer tcpServer(8080);
WiFiClient tcpClient;
Servo servoGaveta, servoCarrinho, servoPorta;
Adafruit_AS726x sensor;
const int PINO_SERVO_GAVETA=18, PINO_SERVO_CARRINHO=19, PINO_SDA=21, PINO_SCL=22;
// Contatos NA entre GPIO e GND. Carcaca: pressionado quando FECHADA.
const int PINO_SERVO_PORTA=23, PINO_FC_PORTA_ABERTA=25;
const int PINO_FC_PORTA_FECHADA=26, PINO_FC_CARCACA_FECHADA=27;
// Calibrar o neutro e o sentido no servo real antes de operar a porta.
const int PORTA_PARAR_US=1500, PORTA_ABRIR_US=1000, PORTA_FECHAR_US=2000;
const int PINO_FC_SENSOR_RECUADO=32, PINO_FC_SENSOR_AVANCADO=33;
const int SENSOR_PARAR_US=1500, SENSOR_AVANCAR_US=1300, SENSOR_RECUAR_US=1700;
const unsigned long FC_DEBOUNCE_MS=30;
bool carrinhoMovendo=false, falhaFinsCarrinho=false;
bool ultimoFcRecuado=false, ultimoFcAvancado=false;
bool portaMovendo=false, falhaCarcaca=false, leituraEmCurso=false, avancandoSensor=false, movendoGaveta=false;
bool carcacaAutorizada=false, carcacaFisicaAnterior=false, sessaoAdmin=false;
int canalAutorizado=-1;
unsigned long renovacaoCarcaca=0;
const unsigned long CARCACA_AUTORIZACAO_TIMEOUT_MS=6000;
bool gavetaConfirmadaFechada=false;
bool movimentoManual=false;
bool ultimoFcAberta=false, ultimoFcFechada=false, ultimoFcCarcaca=false;
struct FimCurso {
  int pino;
  bool bruto=false, ativo=false;
  unsigned long mudouEm=0;
  void atualizar() {
    bool novo=digitalRead(pino)==LOW;
    if (novo!=bruto) { bruto=novo; mudouEm=millis(); }
    if (millis()-mudouEm>=FC_DEBOUNCE_MS) ativo=bruto;
  }
};
FimCurso fcPortaAberta{PINO_FC_PORTA_ABERTA};
FimCurso fcPortaFechada{PINO_FC_PORTA_FECHADA};
FimCurso fcCarcacaFechada{PINO_FC_CARCACA_FECHADA};
FimCurso fcSensorRecuado{PINO_FC_SENSOR_RECUADO};
FimCurso fcSensorAvancado{PINO_FC_SENSOR_AVANCADO};
const int GAVETA_FECHADA=5, GAVETA_ABERTA=175;
int posAtualGaveta=GAVETA_FECHADA;
bool sensorConectado=false, ocupado=false, abortarMovimento=false, emRepouso=false;
String buffers[3];
unsigned long ultimaAtividade=0;
bool watchdogDisparado=false;
uint16_t bufferCanais[6];
uint16_t bufferExtra[6];

// Mantem o dominio optico compativel com o modelo PLS e o validador de metadados.
const uint8_t ACQ_GAIN=GAIN_64X, ACQ_INT_T=50, ACQ_LED_CURRENT=LIMIT_50MA;
const unsigned long ACQ_LED_SETTLE_MS=150, ACQ_TIMEOUT_MS=1500;
const unsigned long ACQ_COLD_IDLE_MS=1500, ACQ_COLD_PREWARM_MS=350;
const int ACQ_OVERSAMPLE_PASSES=2;
const char *ACQ_REVISION="PLS_ACQ_1";
uint32_t sequenciaAquisicao=0;
unsigned long ultimaExposicaoLedMs=0;

bool configuracaoOpticaValida(uint8_t control,uint8_t integration,uint8_t led) {
  return ((control >> 4) & 3)==ACQ_GAIN && ((control >> 2) & 3)==ONE_SHOT &&
         integration==ACQ_INT_T && ((led >> 4) & 3)==ACQ_LED_CURRENT && !(led & 1);
}

void responder(const String &msg) {
  Serial.println(msg);
  if (SerialBT.hasClient()) SerialBT.println(msg);
  if (tcpClient && tcpClient.connected()) tcpClient.println(msg);
}

bool ledLigado=false;
void driverOff() {
  sensor.drvOff();
  if (ledLigado) ultimaExposicaoLedMs=millis();
  ledLigado=false;
}
void driverOn() { sensor.drvOn(); ledLigado=true; }

void enviarDiagnosticoSensor() {
  responder("ESPDIAG:TEMP:"+String(temperatureRead(),1)+
            "|CPU_MHZ:"+String(ESP.getCpuFreqMHz())+
            "|HEAP_FREE:"+String(ESP.getFreeHeap())+
            "|HEAP_TOTAL:"+String(ESP.getHeapSize()));
  if (!sensorConectado || spectrumSensorIoError) {
    responder("DIAG:TEMP:NA|HW:DESCONECTADO|STATUS:ERRO");
    return;
  }
  uint8_t control=0,integration=0,led=0;
  uint8_t temperatura=sensor.readTemperature();
  if (!sensor.readConfiguration(control,integration,led)) {
    responder("DIAG:TEMP:NA|STATUS:ERRO");
    return;
  }
  const float ganhos[4]={1.0,3.7,16.0,64.0};
  const float correntes[4]={12.5,25.0,50.0,100.0};
  responder("DIAG:TEMP:"+String(temperatura)+
            "|GAINCFG:"+String(ganhos[(control >> 4) & 3],1)+"x"+
            "|INTCFG:"+String(integration*2.8f,1)+"ms"+
            "|LEDCFG:"+String(correntes[(led >> 4) & 3],1)+"mA"+
            "|LEDSTATE:"+String((led & 8) ? "ON" : "OFF")+
            "|FULL_NOMINAL_MS:"+String(integration*5.6f,1)+
            "|CONFIG_READBACK:1|FW:"+ACQ_REVISION+"|HW:AS7263_NIR|STATUS:"+
            String(configuracaoOpticaValida(control,integration,led) ? "OK" : "ERRO"));
}

void processarComando(String cmd,int canal);
void enviarEstadoPorta();
void paradaEmergencia();
void pollInputs();

void consumir(Stream &stream, int canal) {
  while (stream.available()) {
    char c=(char)stream.read();
    if (c=='\r') continue;
    if (c=='\n') {
      String command=buffers[canal];
      buffers[canal]="";
      if (command.length()) processarComando(command,canal);
    } else {
      buffers[canal]+=c;
      if (buffers[canal].length()>160) {
        buffers[canal]="";
        responder("STATUS:COMANDO_ERRO:LINHA_LONGA");
      }
    }
  }
}

void pararPorta() {
  if (servoPorta.attached()) {
    servoPorta.writeMicroseconds(PORTA_PARAR_US);
    delay(10);
    servoPorta.detach();
  }
  portaMovendo=false;
}

void pararCarrinho() {
  if (servoCarrinho.attached()) {
    servoCarrinho.writeMicroseconds(SENSOR_PARAR_US);
    delay(10);
    servoCarrinho.detach();
  }
  carrinhoMovendo=false;
}

bool sensorRecuadoConfirmado() {
  return fcSensorRecuado.bruto && fcSensorRecuado.ativo && !fcSensorAvancado.bruto;
}

bool sensorAvancadoConfirmado() {
  return fcSensorAvancado.bruto && fcSensorAvancado.ativo && !fcSensorRecuado.bruto;
}

bool carcacaFisicamenteFechada() {
  return fcCarcacaFechada.bruto && fcCarcacaFechada.ativo;
}

bool carcacaSegura() {
  return carcacaFisicamenteFechada() ||
         (carcacaAutorizada && millis()-renovacaoCarcaca<CARCACA_AUTORIZACAO_TIMEOUT_MS);
}

void revogarCarcaca() {
  bool estavaAutorizada=carcacaAutorizada;
  carcacaAutorizada=false;
  sessaoAdmin=false;
  canalAutorizado=-1;
  if (estavaAutorizada) responder(carcacaFisicamenteFechada() ? "STATUS:CARCACA_AUTORIZACAO_REVOGADA:CARCACA_FECHADA" : "STATUS:CARCACA_AUTORIZACAO_REVOGADA");
}

void atualizarFinsCurso() {
  fcPortaAberta.atualizar();
  fcPortaFechada.atualizar();
  fcCarcacaFechada.atualizar();
  fcSensorRecuado.atualizar();
  fcSensorAvancado.atualizar();
  bool fisicamenteFechada=carcacaFisicamenteFechada();
  if (carcacaFisicaAnterior && !fisicamenteFechada && !sessaoAdmin) {
    revogarCarcaca();
    if (ocupado) abortarMovimento=true;
    gavetaConfirmadaFechada=false;
  }
  carcacaFisicaAnterior=fisicamenteFechada;
  if (carcacaAutorizada && ((fisicamenteFechada && !sessaoAdmin) ||
      millis()-renovacaoCarcaca>=CARCACA_AUTORIZACAO_TIMEOUT_MS ||
      (canalAutorizado==1 && !SerialBT.hasClient()) ||
      (canalAutorizado==2 && (!tcpClient || !tcpClient.connected())))) revogarCarcaca();
  if (!carcacaSegura()) {
    pararPorta();
    servoGaveta.detach();
    pararCarrinho();
    if (sensorConectado && ledLigado) driverOff();
    if (ocupado) abortarMovimento=true;
  }
  if (!fisicamenteFechada && !falhaCarcaca) responder("STATUS:CARCACA_ABERTA");
  if (fisicamenteFechada && falhaCarcaca) responder("STATUS:CARCACA_FECHADA");
  falhaCarcaca=!fisicamenteFechada;
  if ((leituraEmCurso || (avancandoSensor && !movimentoManual)) &&
      (!fcPortaFechada.bruto || fcPortaAberta.bruto)) {
    abortarMovimento=true;
    if (sensorConectado && ledLigado) driverOff();
    pararCarrinho();
  }
  if (!movimentoManual && (portaMovendo || movendoGaveta) && !sensorRecuadoConfirmado()) {
    abortarMovimento=true;
    pararPorta();
    servoGaveta.detach();
    responder("STATUS:CARRINHO_ERRO:REPOUSO_PERDIDO");
  }
  if (leituraEmCurso && (!fcSensorAvancado.bruto || fcSensorRecuado.bruto)) {
    abortarMovimento=true;
    if (sensorConectado && ledLigado) driverOff();
    pararCarrinho();
  }
  if (fcSensorRecuado.bruto && fcSensorAvancado.bruto) {
    pararCarrinho();
    if (ocupado) abortarMovimento=true;
    if (!falhaFinsCarrinho) responder("STATUS:CARRINHO_ERRO:FINS_CONTRADITORIOS");
    falhaFinsCarrinho=true;
  } else falhaFinsCarrinho=false;
  if (portaMovendo && fcPortaAberta.bruto && fcPortaFechada.bruto) {
    pararPorta();
    abortarMovimento=true;
    responder("STATUS:PORTA_ERRO:FINS_CONTRADITORIOS");
  }
  if (ultimoFcAberta!=fcPortaAberta.ativo || ultimoFcFechada!=fcPortaFechada.ativo ||
      ultimoFcCarcaca!=fisicamenteFechada || ultimoFcRecuado!=fcSensorRecuado.ativo ||
      ultimoFcAvancado!=fcSensorAvancado.ativo) {
    ultimoFcAberta=fcPortaAberta.ativo;
    ultimoFcFechada=fcPortaFechada.ativo;
    ultimoFcCarcaca=fisicamenteFechada;
    ultimoFcRecuado=fcSensorRecuado.ativo;
    ultimoFcAvancado=fcSensorAvancado.ativo;
    enviarEstadoPorta();
  }
}

void enviarEstadoPorta() {
  responder("PORTA:ABERTA:"+String(fcPortaAberta.ativo ? 1 : 0)+
            "|FECHADA:"+String(fcPortaFechada.ativo ? 1 : 0)+
            "|CARCACA_FECHADA:"+String(carcacaFisicamenteFechada() ? 1 : 0)+
            "|SENSOR_RECUADO:"+String(fcSensorRecuado.ativo ? 1 : 0)+
            "|SENSOR_AVANCADO:"+String(fcSensorAvancado.ativo ? 1 : 0));
}

void pollInputs() {
  atualizarFinsCurso();
  consumir(Serial,0);
  consumir(SerialBT,1);
  if (tcpServer.hasClient()) {
    WiFiClient novo=tcpServer.available();
    if (!tcpClient || !tcpClient.connected()) {
      if (tcpClient) tcpClient.stop();
      tcpClient=novo;
      buffers[2]="";
    } else novo.stop();
  }
  if (tcpClient && tcpClient.connected()) consumir(tcpClient,2);
}

// Mantem recepcao de emergencia e heartbeat durante esperas.
bool aguardar(unsigned long intervalo,bool interrompivel=true) {
  unsigned long inicio=millis();
  while (millis()-inicio<intervalo) {
    pollInputs();
    if (!carcacaSegura() || (interrompivel && abortarMovimento) ||
        (movendoGaveta && !movimentoManual && (!fcPortaAberta.bruto || fcPortaFechada.bruto))) return false;
    delay(2);
  }
  return true;
}

bool moverPara(Servo &servo,int pino,int &pos,int destino,int intervalo=15,bool interrompivel=true) {
  if (!carcacaSegura()) return false;
  if (pos==destino) {
    servo.attach(pino,500,2400);
    servo.write(destino);
    bool ok=aguardar(1000,interrompivel);
    servo.detach();
    return ok;
  }
  servo.attach(pino,500,2400);
  int step=destino>pos ? 1 : -1;
  bool ok=true;
  while (pos!=destino) {
    pollInputs();
    if (!carcacaSegura() || (interrompivel && abortarMovimento)) { ok=false; break; }
    if (pino==PINO_SERVO_GAVETA && !movimentoManual &&
        (!fcPortaAberta.bruto || !fcPortaAberta.ativo || fcPortaFechada.bruto)) {
      abortarMovimento=true;
      ok=false;
      break;
    }
    pos+=step;
    servo.write(pos);
    if (!aguardar(intervalo,interrompivel)) { ok=false; break; }
  }
  if (ok) ok=aguardar(80,interrompivel);
  servo.detach();
  return ok;
}

bool moverPorta(bool abrir) {
  if (!carcacaSegura()) return false;
  if (fcPortaAberta.bruto && fcPortaFechada.bruto) {
    responder("STATUS:PORTA_ERRO:FINS_CONTRADITORIOS");
    return false;
  }
  FimCurso &destino=abrir ? fcPortaAberta : fcPortaFechada;
  responder(abrir ? "STATUS:ABRINDO_PORTA" : "STATUS:FECHANDO_PORTA");
  // Sem limite de percurso; heartbeat permanece obrigatorio durante movimento.
  while (true) {
    pollInputs();
    if (abortarMovimento || !carcacaSegura()) { pararPorta(); return false; }
    if (millis()-ultimaAtividade>6000) {
      pararPorta();
      abortarMovimento=true;
      responder("STATUS:PORTA_ERRO:COMUNICACAO_PERDIDA");
      return false;
    }
    if (fcPortaAberta.bruto && fcPortaFechada.bruto) {
      pararPorta();
      responder("STATUS:PORTA_ERRO:FINS_CONTRADITORIOS");
      return false;
    }
    if (destino.bruto) {
      // Para no primeiro contato; confirma a chegada apos debounce.
      pararPorta();
      if (destino.ativo) {
        enviarEstadoPorta();
        responder(abrir ? "STATUS:PORTA_ABERTA" : "STATUS:PORTA_FECHADA");
        return true;
      }
    } else {
      if (!servoPorta.attached()) servoPorta.attach(PINO_SERVO_PORTA,500,2400);
      servoPorta.writeMicroseconds(abrir ? PORTA_ABRIR_US : PORTA_FECHAR_US);
      portaMovendo=true;
    }
    delay(2);
  }
}

bool moverCarrinho(bool avancar) {
  if (!carcacaSegura()) return false;
  FimCurso &destino=avancar ? fcSensorAvancado : fcSensorRecuado;
  while (true) {
    pollInputs();
    if (abortarMovimento || !carcacaSegura()) { pararCarrinho(); return false; }
    if (millis()-ultimaAtividade>6000) {
      pararCarrinho();
      abortarMovimento=true;
      responder("STATUS:CARRINHO_ERRO:COMUNICACAO_PERDIDA");
      return false;
    }
    if (fcSensorRecuado.bruto && fcSensorAvancado.bruto) {
      pararCarrinho();
      responder("STATUS:CARRINHO_ERRO:FINS_CONTRADITORIOS");
      return false;
    }
    if (destino.bruto) {
      pararCarrinho();
      if (destino.ativo) {
        enviarEstadoPorta();
        return true;
      }
    } else {
      if (!servoCarrinho.attached()) servoCarrinho.attach(PINO_SERVO_CARRINHO,500,2400);
      servoCarrinho.writeMicroseconds(avancar ? SENSOR_AVANCAR_US : SENSOR_RECUAR_US);
      carrinhoMovendo=true;
    }
    delay(2);
  }
}

void paradaEmergencia() {
  pararPorta();
  pararCarrinho();
  revogarCarcaca();
  ocupado=true;
  emRepouso=true;
  gavetaConfirmadaFechada=false;
  servoGaveta.detach();
  if (sensorConectado) driverOff();
  // Emergencia para os eixos; nao inicia recolhimento nem fechamento.
  abortarMovimento=false;
  ocupado=false;
  emRepouso=false;
  enviarEstadoPorta();
  watchdogDisparado=true;
  responder("STATUS:EMERGENCIA_ACIONADA");
}

bool falharLeitura(const String &id,const String &motivo) {
  driverOff();
  if (spectrumSensorIoError) sensorConectado=false;
  responder("STATUS:LEITURA_ERRO:"+id+":"+motivo);
  return false;
}

bool executarConversaoUnica(uint16_t *destino) {
  unsigned long inicioConv=millis();
  sensor.startMeasurement();
  if (spectrumSensorIoError) return false;
  while (true) {
    bool pronta=sensor.dataReady();
    if (spectrumSensorIoError) return false;
    if (pronta) break;
    if (!aguardar(5)) return false;
    if (millis()-inicioConv>=ACQ_TIMEOUT_MS) return false;
  }
  sensor.readRawValues(destino);
  return !spectrumSensorIoError;
}

bool realizarLeituraEspectral(bool escuro,const String &id) {
  unsigned long inicioTotal=millis();
  if (!sensorConectado || spectrumSensorIoError) {
    responder("STATUS:LEITURA_ERRO:"+id+":SENSOR_DESCONECTADO");
    return false;
  }
  if (!carcacaSegura() || !gavetaConfirmadaFechada || !fcPortaFechada.ativo || !fcPortaFechada.bruto || fcPortaAberta.bruto ||
      posAtualGaveta!=GAVETA_FECHADA || !sensorAvancadoConfirmado()) {
    return falharLeitura(id,"POSICAO_INVALIDA");
  }
  // Garante todos os servos desligados (sem PWM) durante a integracao optica.
  pararPorta();
  pararCarrinho();
  servoGaveta.detach();

  // Confere registradores reais com o LED desligado antes de expor a amostra.
  uint8_t control=0,integration=0,led=0;
  if (!sensor.readConfiguration(control,integration,led)) return falharLeitura(id,"FALHA_I2C");
  if (!configuracaoOpticaValida(control,integration,led) || (led & 8))
    return falharLeitura(id,"CONFIG_OPTICA_DIVERGENTE");
  uint8_t temperatura=sensor.readTemperature();
  if (spectrumSensorIoError) return falharLeitura(id,"FALHA_I2C");
  pollInputs();
  if (abortarMovimento) return falharLeitura(id,"ABORTADA");

  bool ledEstavaFrio=!escuro && (ultimaExposicaoLedMs==0 || (millis()-ultimaExposicaoLedMs)>ACQ_COLD_IDLE_MS);
  if (escuro) driverOff(); else driverOn();
  if (spectrumSensorIoError) return falharLeitura(id,"FALHA_I2C");

  // Pre-condicionamento termico no primeiro disparo do lote quando o LED parte frio:
  // executa estabilizacao extra + 1 conversao descartada (dummy scan) para eliminar a rampa nos disparos 1-3.
  if (ledEstavaFrio) {
    if (!aguardar(ACQ_COLD_PREWARM_MS)) return falharLeitura(id,"ABORTADA");
    unsigned long inicioDummy=millis();
    sensor.startMeasurement();
    if (spectrumSensorIoError) return falharLeitura(id,"FALHA_I2C");
    while (true) {
      bool pronta=sensor.dataReady();
      if (spectrumSensorIoError) return falharLeitura(id,"FALHA_I2C");
      if (pronta) break;
      if (!aguardar(5)) return falharLeitura(id,"ABORTADA");
      if (millis()-inicioDummy>=ACQ_TIMEOUT_MS) return falharLeitura(id,"TIMEOUT");
    }
    sensor.readRawValues(bufferExtra);
    if (spectrumSensorIoError) return falharLeitura(id,"FALHA_I2C");
  }

  if (!aguardar(ACQ_LED_SETTLE_MS)) return falharLeitura(id,"ABORTADA");
  if (!sensor.readConfiguration(control,integration,led)) return falharLeitura(id,"FALHA_I2C");
  if (!configuracaoOpticaValida(control,integration,led) || bool(led & 8)!=!escuro)
    return falharLeitura(id,"CONFIG_OPTICA_DIVERGENTE");

  // Dupla conversao (2x oversampling) com media arredondada para reduzir ruido de quantizacao em 760-860 nm.
  uint32_t acumulador[6]={0,0,0,0,0,0};
  unsigned long inicio=millis();
  for (int passo=0; passo<ACQ_OVERSAMPLE_PASSES; passo++) {
    unsigned long inicioPasso=millis();
    sensor.startMeasurement();
    if (spectrumSensorIoError) return falharLeitura(id,"FALHA_I2C");
    while (true) {
      bool pronta=sensor.dataReady();
      if (spectrumSensorIoError) return falharLeitura(id,"FALHA_I2C");
      if (pronta) break;
      if (!aguardar(5)) return falharLeitura(id,"ABORTADA");
      if (millis()-inicioPasso>=ACQ_TIMEOUT_MS) return falharLeitura(id,"TIMEOUT");
    }
    sensor.readRawValues(bufferCanais);
    if (spectrumSensorIoError) return falharLeitura(id,"FALHA_I2C");
    for (int i=0;i<6;i++) {
      if (bufferCanais[i]>=65500) return falharLeitura(id,"SATURACAO");
      acumulador[i]+=bufferCanais[i];
    }
  }
  for (int i=0;i<6;i++) {
    bufferCanais[i]=(uint16_t)((acumulador[i] + (ACQ_OVERSAMPLE_PASSES/2)) / ACQ_OVERSAMPLE_PASSES);
  }
  unsigned long duracaoConversao=millis()-inicio;
  driverOff();
  if (spectrumSensorIoError) return falharLeitura(id,"FALHA_I2C");
  // Service emergency/contacts again after synchronous sensor transfers.
  pollInputs();
  if (abortarMovimento) return falharLeitura(id,"ABORTADA");
  if (!carcacaSegura() || !fcPortaFechada.bruto || fcPortaAberta.bruto ||
      !sensorAvancadoConfirmado()) return falharLeitura(id,"POSICAO_INVALIDA");
  if (!sensor.readConfiguration(control,integration,led)) return falharLeitura(id,"FALHA_I2C");
  if (!configuracaoOpticaValida(control,integration,led) || (led & 8))
    return falharLeitura(id,"CONFIG_OPTICA_DIVERGENTE");
  for (int i=0;i<6;i++)
    if (bufferCanais[i]>=65500) return falharLeitura(id,"SATURACAO");

  // Additive packet: old SCAN and completion framing stays unchanged.
  String meta="SCANMETA:"+id+"|V:1|FW:"+ACQ_REVISION+
    "|SEQ:"+String(++sequenciaAquisicao)+"|KIND:"+String(escuro ? "DARK" : "LIGHT")+
    "|GAIN_CODE:"+String((control >> 4) & 3)+"|INT_T:"+String(integration)+
    "|LED_CODE:"+String((led >> 4) & 3)+"|LED_WAIT_MS:"+String(ACQ_LED_SETTLE_MS)+
    "|TEMP_C:"+String(temperatura)+"|UPTIME_MS:"+String(inicioTotal)+
    "|CONVERSION_MS:"+String(duracaoConversao)+"|TOTAL_MS:"+String(millis()-inicioTotal)+
    "|EXPOSURE_LED:"+String(escuro ? "OFF" : "ON")+"|READBACK:1|QUALITY:OK";
  responder(meta);
  String payload="SCAN:"+id+"|DATA:";
  for (int i=0;i<6;i++) {
    payload+=String(bufferCanais[i]);
    if (i<5) payload+=",";
  }
  responder(payload);
  responder("STATUS:LEITURA_CONCLUIDA:"+id);
  return true;
}

void processarComando(String cmd,int canal) {
  cmd.trim();
  bool comandoManual=cmd.startsWith("CMD:MANUAL:");
  if (comandoManual) {
    cmd="CMD:"+cmd.substring(11);
    if (cmd!="CMD:ABRIR_PORTA" && cmd!="CMD:FECHAR_PORTA" &&
        cmd!="CMD:ABRIR_GAVETA" && cmd!="CMD:FECHAR_GAVETA" &&
        cmd!="CMD:AVANCAR_SENSOR" && cmd!="CMD:RECUAR_SENSOR") {
      responder("STATUS:COMANDO_ERRO:MANUAL_INVALIDO");
      return;
    }
  }
  ultimaAtividade=millis();
  watchdogDisparado=false;
  if (cmd=="CMD:PING" || cmd=="PING") {
    responder("STATUS:PROTOCOLO_2");
    responder("STATUS:AQUISICAO_META_1");
    responder("STATUS:PORTA_PROTOCOLO_1");
    responder("STATUS:MANUAL_PROTOCOLO_1");
    responder("STATUS:CARRINHO_PROTOCOLO_1");
    responder("STATUS:ADMIN_PROTOCOLO_1");
    enviarEstadoPorta();
    responder(sensorConectado ? "STATUS:SENSOR_OK" : "STATUS:SENSOR_ERRO");
    responder("STATUS:PONG");
    return;
  }
  if (cmd=="CMD:EMERGENCIA" || cmd=="CMD:REPOUSO_SUAVE") {
    abortarMovimento=true;
    pararPorta();
    pararCarrinho();
    if (sensorConectado) driverOff();
    if (!ocupado) paradaEmergencia();
    return;
  }
  // O supervisorio valida usuario/senha; nenhuma senha trafega no protocolo.
  // A autorizacao fica restrita ao transporte de origem e requer renovacao.
  if (cmd=="CMD:ADMIN_CARCACA") {
    if (ocupado || (carcacaAutorizada && canal!=canalAutorizado)) {
      responder("STATUS:COMANDO_ERRO:AUTORIZACAO_INDISPONIVEL");
    } else {
      sessaoAdmin=true;
      carcacaAutorizada=true;
      canalAutorizado=canal;
      renovacaoCarcaca=millis();
      responder("STATUS:ADMIN_CARCACA_AUTORIZADA");
    }
    return;
  }
  if (cmd=="CMD:AUTORIZAR_CARCACA") {
    if (ocupado || carcacaFisicamenteFechada() || (carcacaAutorizada && canal!=canalAutorizado)) {
      responder("STATUS:COMANDO_ERRO:AUTORIZACAO_INDISPONIVEL");
    } else {
      carcacaAutorizada=true;
      canalAutorizado=canal;
      renovacaoCarcaca=millis();
      responder("STATUS:CARCACA_AUTORIZADA");
    }
    return;
  }
  if (cmd=="CMD:RENOVAR_CARCACA") {
    if (carcacaAutorizada && canal==canalAutorizado) renovacaoCarcaca=millis();
    return;
  }
  if (cmd=="CMD:REVOGAR_CARCACA") {
    if (canal==canalAutorizado) {
      revogarCarcaca();
      if (ocupado && !carcacaFisicamenteFechada()) abortarMovimento=true;
    }
    return;
  }
  if (cmd=="CMD:ESTADO_PORTA" || cmd=="CMD:ESTADO_CARRINHO") {
    enviarEstadoPorta();
    return;
  }
  if ((!carcacaSegura() || (!carcacaFisicamenteFechada() && canal!=canalAutorizado)) && cmd!="CMD:DIAG_SENSOR") {
    responder("STATUS:COMANDO_ERRO:CARCACA_ABERTA");
    return;
  }
  if (ocupado) {
    responder("STATUS:COMANDO_ERRO:OCUPADO");
    return;
  }
  ocupado=true;
  movimentoManual=comandoManual;
  bool ok=true;
  if (cmd=="CMD:ABRIR_PORTA" || cmd=="CMD:FECHAR_PORTA") {
    if (!comandoManual && !sensorRecuadoConfirmado()) {
      responder("STATUS:COMANDO_ERRO:SENSOR_NAO_RECUADO");
      ok=false;
    } else if (!comandoManual && cmd=="CMD:FECHAR_PORTA" && !gavetaConfirmadaFechada) {
      responder("STATUS:COMANDO_ERRO:GAVETA_NAO_FECHADA");
      ok=false;
    } else ok=moverPorta(cmd=="CMD:ABRIR_PORTA");
  } else if (cmd=="CMD:ABRIR_GAVETA" || cmd=="CMD:FECHAR_GAVETA") {
    if (!comandoManual && !sensorRecuadoConfirmado()) {
      responder("STATUS:COMANDO_ERRO:SENSOR_NAO_RECUADO");
      ok=false;
    } else if (!comandoManual && (!fcPortaAberta.ativo || !fcPortaAberta.bruto || fcPortaFechada.bruto)) {
      responder("STATUS:COMANDO_ERRO:PORTA_NAO_ABERTA");
      ok=false;
    } else {
      bool abrir=cmd=="CMD:ABRIR_GAVETA";
      gavetaConfirmadaFechada=false;
      responder(abrir ? "STATUS:ABRINDO_GAVETA" : "STATUS:FECHANDO_GAVETA");
      movendoGaveta=true;
      ok=moverPara(servoGaveta,PINO_SERVO_GAVETA,posAtualGaveta,
                   abrir ? GAVETA_ABERTA : GAVETA_FECHADA,18);
      movendoGaveta=false;
      gavetaConfirmadaFechada=ok && !abrir;
      if (ok) responder(abrir ? "STATUS:GAVETA_ABERTA" : "STATUS:GAVETA_FECHADA");
    }
  } else if (cmd=="CMD:AVANCAR_SENSOR") {
    if (!comandoManual && (!fcPortaFechada.ativo || !fcPortaFechada.bruto || fcPortaAberta.bruto)) {
      responder("STATUS:COMANDO_ERRO:PORTA_NAO_FECHADA");
      ok=false;
    } else if (!comandoManual && (!gavetaConfirmadaFechada || posAtualGaveta!=GAVETA_FECHADA)) {
      responder("STATUS:COMANDO_ERRO:GAVETA_NAO_FECHADA");
      ok=false;
    } else {
      responder("STATUS:POSICIONANDO_SENSOR");
      avancandoSensor=true;
      ok=moverCarrinho(true);
      avancandoSensor=false;
      if (ok) responder("STATUS:SENSOR_AVANCADO");
    }
  } else if (cmd=="CMD:RECUAR_SENSOR") {
    responder("STATUS:RECUANDO_SENSOR");
    ok=moverCarrinho(false);
    if (ok) responder("STATUS:SENSOR_RECUADO");
  } else if (cmd.startsWith("CMD:LER_ESPECTRO:") || cmd.startsWith("CMD:LER_ESCURO:")) {
    bool escuro=cmd.startsWith("CMD:LER_ESCURO:");
    String id=cmd.substring(cmd.lastIndexOf(':')+1);
    bool valido=id.length()>0 && id.length()<=64;
    for (unsigned int i=0;i<id.length();i++)
      valido=valido && (isAlphaNumeric(id[i]) || id[i]=='_' || id[i]=='-');
    if (!valido) responder("STATUS:COMANDO_ERRO:ID_INVALIDO");
    else {
      leituraEmCurso=true;
      ok=realizarLeituraEspectral(escuro,id);
      leituraEmCurso=false;
    }
  } else if (cmd=="CMD:DIAG_SENSOR") {
    enviarDiagnosticoSensor();
  } else {
    responder("STATUS:COMANDO_ERRO:COMANDO_DESCONHECIDO");
    ok=false;
  }
  movimentoManual=false;
  ocupado=false;
  if (abortarMovimento) paradaEmergencia();
}

void setup() {
  Serial.begin(115200);
  SerialBT.begin("Bancada_NIR_ESP32");
  WiFi.softAP("Bancada_NIR_AP");
  tcpServer.begin();
  Wire.begin(PINO_SDA,PINO_SCL);
  Wire.setTimeOut(50);
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  servoGaveta.setPeriodHertz(50);
  servoCarrinho.setPeriodHertz(50);
  servoPorta.setPeriodHertz(50);
  pinMode(PINO_FC_PORTA_ABERTA,INPUT_PULLUP);
  pinMode(PINO_FC_PORTA_FECHADA,INPUT_PULLUP);
  pinMode(PINO_FC_CARCACA_FECHADA,INPUT_PULLUP);
  pinMode(PINO_FC_SENSOR_RECUADO,INPUT_PULLUP);
  pinMode(PINO_FC_SENSOR_AVANCADO,INPUT_PULLUP);
  pararCarrinho();
  pararPorta();
  fcPortaAberta.atualizar();
  fcPortaFechada.atualizar();
  fcCarcacaFechada.atualizar();
  fcSensorRecuado.atualizar();
  fcSensorAvancado.atualizar();
  delay(FC_DEBOUNCE_MS);
  atualizarFinsCurso();
  // Todos os eixos permanecem parados e sem PWM ao ligar.
  ocupado=false;
  abortarMovimento=false;
  spectrumSensorIoError=false;
  sensorConectado=sensor.begin() && !spectrumSensorIoError;
  if (sensorConectado) {
    sensor.setGain(ACQ_GAIN);
    sensor.setIntegrationTime(ACQ_INT_T);
    sensor.setDrvCurrent(ACQ_LED_CURRENT);
    sensor.setConversionType(ONE_SHOT);
    sensor.indicateLED(false);
    driverOff();
    uint8_t control=0,integration=0,led=0;
    if (!sensor.readConfiguration(control,integration,led) ||
        !configuracaoOpticaValida(control,integration,led) || (led & 8)) sensorConectado=false;
  }
  responder("STATUS:PROTOCOLO_2");
  responder("STATUS:AQUISICAO_META_1");
  responder("STATUS:PORTA_PROTOCOLO_1");
  responder("STATUS:MANUAL_PROTOCOLO_1");
  responder("STATUS:CARRINHO_PROTOCOLO_1");
  responder("STATUS:ADMIN_PROTOCOLO_1");
  enviarEstadoPorta();
  responder(sensorConectado ? "STATUS:SENSOR_OK" : "STATUS:SENSOR_ERRO");
  ultimaAtividade=millis();
}

void loop() {
  pollInputs();
  if (!ocupado && !watchdogDisparado && millis()-ultimaAtividade>6000 &&
      (posAtualGaveta!=GAVETA_FECHADA || carrinhoMovendo || portaMovendo)) {
    paradaEmergencia();
  }
  delay(2);
}
