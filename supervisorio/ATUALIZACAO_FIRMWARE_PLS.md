# SpectrumLinux — aquisição ESP32 para PLS (PLS_ACQ_1)

Atualização local de 04/11/2026. O firmware e o supervisório foram atualizados em conjunto. Nenhuma gravação na placa nem ensaio físico foi realizado nesta sessão.

## Resultado implementado

O uso permanece com a amostra na posição e orientação marcadas no berço e cinco aquisições estáticas. O PLS com SNV continua opcional e inicia desligado.

O ESP32 agora:

- Configura aquisição única desde a inicialização. Cada `startMeasurement` limpa DATA_RDY e solicita a conversão completa em uma única escrita no registrador, sem passar brevemente pelo modo contínuo anterior.
- Confere os registradores reais de ganho, integração, corrente configurada de LED, modo de conversão e LED indicador. A conferência acontece ao inicializar, antes da exposição, depois da espera de estabilização e após a leitura.
- Verifica o registrador do LED de iluminação ligado para amostra e desligado para escuro. Essa é uma verificação digital da configuração: não mede fisicamente a emissão luminosa.
- Interrompe a aquisição assim que detecta erro I²C, distinguindo a falha de um timeout de conversão.
- Reavalia emergência/contatos após a transferência síncrona dos seis canais e descarta o resultado quando há perda da posição.
- Publica metadados por ID, com revisão do firmware, sequência, tipo claro/escuro, configuração lida, temperatura interna do sensor, tempo de conversão/leitura e duração total. A sequência antiga `SCAN:id|DATA:...` / `LEITURA_CONCLUIDA:id` permanece compatível.
- Rejeita saturação ou divergência de configuração, publicando erro em vez de dados.

O supervisório agora:

- Reconhece `AQUISICAO_META_1` no handshake e exige metadados correspondentes antes de aceitar a conclusão da leitura desse firmware.
- Rejeita metadados duplicados, configurações divergentes, tipo de leitura incorreto, sequência repetida dentro do lote e conclusão sem dados novos. Pacotes de IDs antigos são descartados.
- Preserva associação entre ID, ADC e metadados das cinco aquisições, inclusive no fluxo de repetibilidade.
- Inclui a proveniência no registro do ensaio e no JSON de comparação PLS. Firmware anterior continua compatível e aparece como sem metadados de aquisição.
- Mostra o desvio padrão das previsões PLS entre as aquisições estáticas. É um indicador de repetibilidade e não uma incerteza analítica validada. O resultado central continua sendo o PLS sobre o espectro médio, como no conjunto de treino.

## Condições ópticas e modelo

Foram mantidos ganho 64x, integração INT_T=50 (140 ms por banco; aproximadamente 280 ms nominais para seis bandas), corrente configurada 50 mA e espera mínima de estabilização de 150 ms. Não há exposição automática, suavização de ADC nem mudança dos coeficientes para aproximar artificialmente o Kappa de referência.

A nova conferência de registradores acrescenta acessos I²C e muda ligeiramente a temporização de aquisição. Após instalar o firmware, refaça branco/escuro e repita as amostras de referência na posição marcada para verificar transferência do modelo. Se houver deslocamento sistemático, forme um conjunto identificado da nova campanha para treinar e validar novamente.

O modelo SNV e os dados de treino desta sessão foram preservados. A avaliação anterior continua sendo RMSE agrupado 2,154, MAE 1,844, R² 0,920, com quatro amostras físicas e um componente fixado previamente. Essas métricas descrevem os dados anteriores; não demonstram o desempenho físico do novo firmware. A proximidade ao Kappa laboratorial após a atualização ainda precisa ser medida.

Eldorado 0,58 continua PRESUMIDO e excluído do treino e das métricas. As três posições históricas de 19,28 permanecem agrupadas como uma única amostra física.

## Compilação para Arduino IDE

- Placa usada para verificar a compilação: **ESP32 Dev Module**, ESP32 clássico.
- **Partition Scheme: Huge APP (3MB No OTA/1MB SPIFFS)**, conforme configuração informada pelo usuário.
- FQBN: `esp32:esp32:esp32:PartitionScheme=huge_app`.
- Pacote ESP32 3.3.12, ESP32Servo 3.2.1 e Adafruit BusIO 1.17.4, já instalados no computador.
- Código compilado: **1.677.163 bytes (53% de 3.145.728)**; variáveis globais: **65.232 bytes (19%)**.
- O projeto usa USB, Wi-Fi e Bluetooth SPP do ESP32 clássico. Os binários não são destinados a ESP32-S2/S3/C3.

O sketch atualizado mantém o caminho `Firmware_ESP32_4_16_2/sketch_sep4a_copy_20261008183551/sketch_sep4a_copy_20261008183551.ino`. A pasta histórica foi mantida por compatibilidade; a revisão efetiva aparece como `PLS_ACQ_1` na telemetria.

Com Arduino CLI instalado, o equivalente é:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32:PartitionScheme=huge_app Firmware_ESP32_4_16_2/sketch_sep4a_copy_20261008183551
```

Não foi realizada gravação. Para usar o novo protocolo, grave o sketch pelo Arduino IDE com Huge APP e inicie o supervisório atualizado por `INICIAR_EXPERIMENTAL.sh`. O executável antigo de PC em `dist` foi preservado.

## Verificação e reversibilidade

**34 testes passaram; 15 subtestes passaram.** Incluem SNV/MSC/PLS, separação por amostra física, preservação da calibração, fluxo de leitura e vínculo entre metadados e ADC. Um teste compila e executa a rotina C++ real com sensor simulado em dez cenários: claro, escuro, integração divergente, LED sem o estado esperado, mudança de configuração após captura, saturação, falha I²C, timeout, perda de posição e interrupção.

A compilação completa ESP32 com Huge APP passou. Na revisão do diff, 12 funções de movimento, intertravamento, emergência e polling foram comparadas ao código anterior e permaneceram idênticas. Pinos, sentidos, neutros e limites dos motores foram preservados. Arquivos de calibração e modelos não foram regravados.

Branch local: `experimental/chemometrics-snv-20261104`. O commit desta revisão permite retornar à versão PLS anterior sem alteração de aquisição. Também há backup dos arquivos substituídos. Para reverter o ESP32 depois de gravá-lo, é necessário gravar novamente o firmware anterior; voltar apenas o código no Git não troca o programa da placa.

Persistem limitações do hardware: uma falha I²C pode impedir o comando de desligamento do LED, e o driver ainda tem acessos síncronos com timeout. O novo código rejeita a leitura e informa a falha, mas não cria um desligamento físico independente. A temperatura registrada é interna ao sensor, não da amostra. Nenhum limiar de qualidade ou ganho de exatidão foi validado industrialmente.

Referência técnica: [datasheet oficial AS7263 — conversão por bancos e registradores](https://look.ams-osram.com/m/2f885f8e1b074032/original/AS7263-DS000476.pdf).
