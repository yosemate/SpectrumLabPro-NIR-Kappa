"""Parse per-scan ESP32 acquisition provenance; never transform spectral ADC data."""
import re

EXPECTED = {'V': 1, 'GAIN_CODE': 3, 'INT_T': 50, 'LED_CODE': 2,
            'LED_WAIT_MS': 150, 'READBACK': 1}
INTEGER_FIELDS = set(EXPECTED) | {'SEQ','TEMP_C','UPTIME_MS','CONVERSION_MS','TOTAL_MS'}


def parse_scan_metadata(line, expected_id, dark=False):
    if len(line)>1024 or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', expected_id):
        raise ValueError('Metadados de aquisição inválidos.')
    fields=line.strip().split('|')
    if fields[0] != 'SCANMETA:'+expected_id:
        raise ValueError('Metadados de outro identificador de aquisição.')
    data={}
    for field in fields[1:]:
        if ':' not in field:
            raise ValueError('Campo de aquisição incompleto.')
        key,value=field.split(':',1)
        if key in data:
            raise ValueError('Campo de aquisição duplicado.')
        data[key]=value
    if not (INTEGER_FIELDS | {'FW','KIND','QUALITY','EXPOSURE_LED'}).issubset(data):
        raise ValueError('Metadados de aquisição incompletos.')
    for key in INTEGER_FIELDS:
        if not re.fullmatch(r'\d+', data[key]):
            raise ValueError('Valor de aquisição inválido: '+key)
        data[key]=int(data[key])
    if any(data[k]!=v for k,v in EXPECTED.items()):
        raise ValueError('Configuração óptica difere do domínio de treino do PLS.')
    if data['FW']!='PLS_ACQ_1' or data['QUALITY']!='OK':
        raise ValueError('Revisão ou qualidade de aquisição incompatível.')
    if data['KIND']!=('DARK' if dark else 'LIGHT') or data['EXPOSURE_LED']!=('OFF' if dark else 'ON'):
        raise ValueError('Tipo da aquisição ou estado do LED incompatível.')
    if not (1<=data['SEQ']<=0xffffffff and 0<=data['UPTIME_MS']<=0xffffffff and 0<=data['TEMP_C']<=255):
        raise ValueError('Sequência, horário ou temperatura inválidos.')
    if not (0<data['CONVERSION_MS']<=4000 and
            data['CONVERSION_MS']+data['LED_WAIT_MS']<=data['TOTAL_MS']<=4000):
        raise ValueError('Tempos de aquisição inconsistentes.')
    data['scan_id']=expected_id
    return data
