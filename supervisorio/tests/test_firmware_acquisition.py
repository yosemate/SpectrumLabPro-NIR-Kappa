"""Execute the real firmware acquisition routine with deterministic sensor faults."""
from pathlib import Path
import shutil,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
SKETCH=ROOT/'Firmware_ESP32_4_16_2/sketch_sep4a_copy_20261008183551/sketch_sep4a_copy_20261008183551.ino'
def function(source,name):
    start=source.index('bool '+name+'(');opening=source.index('{',start);depth=1;i=opening+1
    while depth:
        depth+=(source[i]=='{')-(source[i]=='}');i+=1
    return source[start:i]
HARNESS=r'''
#include <cstdint>
#include <string>
#include <vector>
#include <cassert>
#include <iostream>
#include <type_traits>
class String {public: std::string value;
 String(const char*s):value(s){} String(const std::string&s):value(s){}
 template<class T,typename std::enable_if<std::is_integral<T>::value,int>::type=0>
 String(T n):value(std::to_string(n)){}
 String&operator+=(const String&s){value+=s.value;return *this;}};
String operator+(const String&a,const String&b){return String(a.value+b.value);}
uint32_t clockMs=0;unsigned long millis(){return clockMs;}
bool spectrumSensorIoError=false,sensorConectado=true,abortarMovimento=false,ledLigado=false;
bool gavetaConfirmadaFechada=true,closed=true,advanced=true;
struct Contact{bool ativo=true,bruto=true;}fcPortaFechada;
Contact fcPortaAberta{false,false};
const int GAVETA_FECHADA=5;int posAtualGaveta=5;
const uint8_t GAIN_64X=3,ONE_SHOT=3,LIMIT_50MA=2;
const uint8_t ACQ_GAIN=GAIN_64X,ACQ_INT_T=50,ACQ_LED_CURRENT=LIMIT_50MA;
const unsigned long ACQ_LED_SETTLE_MS=150,ACQ_TIMEOUT_MS=1500;
const char*ACQ_REVISION="PLS_ACQ_1";uint32_t sequenciaAquisicao=0;
uint16_t bufferCanais[6];std::vector<std::string>messages;
struct Sensor{
 uint8_t integration=50,gain=3,current=2,bank=3;
 bool on=false,started=false,neverReady=false,ioReady=false,saturated=false;
 bool ledStuckOff=false,driftAfterRaw=false,lostPositionAfterRaw=false;uint32_t start=0;
 bool readConfiguration(uint8_t&c,uint8_t&i,uint8_t&l){c=(gain<<4)|(bank<<2);i=integration;l=(current<<4)|(on?8:0);return !spectrumSensorIoError;}
 uint8_t readTemperature(){return 28;}
 void drvOff(){on=false;}void drvOn(){on=!ledStuckOff;}
 void startMeasurement(){started=true;start=clockMs;}
 bool dataReady(){if(ioReady){spectrumSensorIoError=true;return false;}return !neverReady&&started&&uint32_t(clockMs-start)>=280;}
 void readRawValues(uint16_t*b){for(int i=0;i<6;i++)b[i]=saturated?65535:(on?100+i:0);if(driftAfterRaw)integration=25;if(lostPositionAfterRaw)advanced=false;}
}sensor;
void responder(const String&s){messages.push_back(s.value);}
void driverOff(){sensor.drvOff();ledLigado=false;}void driverOn(){sensor.drvOn();ledLigado=true;}
bool carcacaSegura(){return closed;}bool sensorAvancadoConfirmado(){return advanced;}
void pollInputs(){}bool aguardar(unsigned long ms){clockMs+=ms;return !abortarMovimento;}
'''
TRIALS=r'''
void reset(){clockMs=0;spectrumSensorIoError=false;sensorConectado=true;abortarMovimento=false;ledLigado=false;closed=true;advanced=true;gavetaConfirmadaFechada=true;sensor=Sensor();messages.clear();}
void rejected(const char*reason){assert(!sensor.on);assert(!messages.empty());assert(messages.back().find(reason)!=std::string::npos);
 for(auto&m:messages){assert(m.find("SCAN:")!=0);assert(m.find("SCANMETA:")!=0);assert(m.find("LEITURA_CONCLUIDA")==std::string::npos);}}
int main(){
 reset();assert(realizarLeituraEspectral(false,"light"));assert(!sensor.on);assert(messages.size()==3);
 assert(messages[0].find("SCANMETA:light|")==0);assert(messages[0].find("|CONVERSION_MS:280|")!=std::string::npos);assert(messages[0].find("|EXPOSURE_LED:ON|")!=std::string::npos);
 assert(messages[1]=="SCAN:light|DATA:100,101,102,103,104,105");assert(messages[2]=="STATUS:LEITURA_CONCLUIDA:light");
 reset();assert(realizarLeituraEspectral(true,"dark"));assert(messages[0].find("|KIND:DARK|")!=std::string::npos);assert(messages[0].find("|EXPOSURE_LED:OFF|")!=std::string::npos);assert(messages[1]=="SCAN:dark|DATA:0,0,0,0,0,0");
 reset();sensor.integration=25;assert(!realizarLeituraEspectral(false,"bad"));rejected("CONFIG_OPTICA_DIVERGENTE");
 reset();sensor.ledStuckOff=true;assert(!realizarLeituraEspectral(false,"bad"));rejected("CONFIG_OPTICA_DIVERGENTE");
 reset();sensor.driftAfterRaw=true;assert(!realizarLeituraEspectral(false,"bad"));rejected("CONFIG_OPTICA_DIVERGENTE");
 reset();sensor.saturated=true;assert(!realizarLeituraEspectral(false,"bad"));rejected("SATURACAO");
 reset();sensor.ioReady=true;assert(!realizarLeituraEspectral(false,"bad"));rejected("FALHA_I2C");assert(!sensorConectado);
 reset();sensor.neverReady=true;assert(!realizarLeituraEspectral(false,"bad"));rejected("TIMEOUT");
 reset();sensor.lostPositionAfterRaw=true;assert(!realizarLeituraEspectral(false,"bad"));rejected("POSICAO_INVALIDA");
 reset();abortarMovimento=true;assert(!realizarLeituraEspectral(false,"bad"));rejected("ABORTADA");
 std::cout<<"10 acquisition scenarios passed\n";}
'''
class FirmwareAcquisitionTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('g++'),'Native C++ compiler unavailable')
    def test_acquisition_with_sensor_and_position_faults(self):
        source=SKETCH.read_text();code=HARNESS+'\n'+'\n'.join(function(source,n) for n in ('configuracaoOpticaValida','falharLeitura','realizarLeituraEspectral'))+TRIALS
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'acquisition.cpp';path.write_text(code);binary=Path(tmp)/'acquisition'
            built=subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror',str(path),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)
            self.assertIn('10 acquisition scenarios passed',ran.stdout)
