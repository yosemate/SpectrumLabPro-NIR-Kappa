# Revisão implementada

Os pontos de aquisição descritos abaixo foram implementados e testados na revisão PLS_ACQ_1. Consulte `ATUALIZACAO_FIRMWARE_PLS.md` para estado atual, compilação Huge APP e limites. A análise abaixo é o registro anterior à implementação.

# Firmware ESP32 e qualidade dos espectros para PLS

Análise estática do firmware local `Firmware_ESP32_4_16_2/sketch_sep4a_copy_20261008183551`, incluindo o driver `src/Adafruit_AS726x.cpp`. Firmware não modificado, não compilado e não gravado no ESP32 nesta atualização. Não foi feita medição temporal ou elétrica no hardware.

O PLS e a normalização devem continuar no supervisório. Colocá-los no ESP32 não acrescentaria informação às seis bandas e dificultaria rastreabilidade e comparação.

## O que já está adequado

- Parâmetros fixos: ganho 64x, integração 50 × 2,8 ms e corrente configurada de LED 50 mA. Mantê-los nesta fase preserva a comparabilidade com os espectros de treino.
- `realizarLeituraEspectral` liga/desliga o LED conforme amostra/escuro, aguarda 150 ms e chama `startMeasurement` (`.ino`, linhas 373–375).
- Apesar de `setup` usar MODE_2, o driver limpa DATA_RDY e muda para ONE_SHOT em cada `startMeasurement` (`.cpp`, linhas 195–200). Portanto, não é correto afirmar que as leituras exportadas permanecem simplesmente em modo contínuo.
- Há espera por DATA_RDY, limite de 1500 ms e desligamento do LED; resultados com erro I²C ou canal ≥65500 não são publicados (`.ino`, linhas 377–397).
- O resultado tem ID e confirmação correspondente (`SCAN:id|DATA:...` e `LEITURA_CONCLUIDA:id`), e só é adquirido com os intertravamentos de posição previstos no código.
- O sensor permanece parado durante as cinco leituras controladas pelo supervisório. O reposicionamento manual da amostra não deve ser convertido em três referências laboratoriais independentes.

## Melhorias prioritárias para uma próxima revisão

| Prioridade | Evidência no código | Melhoria e efeito esperado |
|---|---|---|
| Alta | Diagnóstico informa valores literais GAINCFG/INTCFG/LEDCFG, separados da configuração real (`enviarDiagnosticoSensor`) | Ler os registradores após configurar o sensor e anexar configuração, versão e temperatura a cada aquisição. Evita aceitar silenciosamente uma configuração diferente da usada no treino. Exige extensão compatível no parser do supervisório. |
| Alta | `realizarLeituraEspectral` só trata explicitamente a falha I²C depois de sair da espera de DATA_RDY | Verificar o sinal de falha logo após ligar o LED, iniciar conversão e consultar DATA_RDY. Hoje uma falha durante a espera pode acabar rotulada TIMEOUT antes de chegar ao bloco FALHA_I2C. Não usar esse lote para alimentar o modelo. |
| Média | Driver faz espera síncrona de até cerca de 200 ms por acesso virtual, chamando `yield()` (`.cpp`, linhas 313–379) | Medir a latência real e considerar uma máquina de estados I²C cooperativa. `yield()` não chama o `pollInputs()` da aplicação; a latência de emergência/contatos durante acesso ao sensor precisa ser avaliada em bancada. A falha é limitada por timeout, mas isso não equivale a resposta instantânea. |
| Média | Há atraso fixo de 150 ms para estabilização e nenhum registro de duração/temperatura no pacote SCAN | Registrar início/fim da integração, temperatura e ordem da aquisição. Testar primeiro versus demais scans e deriva de branco. Só mudar tempo de estabilização após ensaio, com nova referência óptica e dados de comparação. |
| Média | Firmware rejeita apenas saturação; estatística e mínimo de sinal são tratados no Python | Preservar valores brutos e acrescentar sinalizadores de qualidade por canal, mantendo critérios finais no supervisório. Não inventar um limiar de SNR a partir de um único relatório. |
| Experimental | Há só seis canais, com sinais e respostas diferentes por banda | Avaliar outro tempo de integração apenas em uma campanha separada, com branco/escuro e novas referências. Não implementar ganho/exposição automáticos no modelo atual: isso mudaria o domínio dos dados e exigiria rastreabilidade e recalibração. |

A integração configurada é **140 ms por banco**, não necessariamente 140 ms para o espectro completo. O AS7263 precisa de duas integrações para reunir as seis bandas: nominalmente **280 ms**, além da estabilização do LED, acessos I²C e comunicação. Isso ajuda a interpretar duração e aquisições; não exige mudar o valor 50 já usado no treino. Ver [datasheet oficial AS7263, seção Data Conversion Description e Integration Time Register](https://look.ams-osram.com/m/2f885f8e1b074032/original/AS7263-DS000476.pdf).

As cinco aquisições estáticas e o bom CV do sinal não garantem representatividade espacial nem exatidão do Kappa. A maior contribuição imediata para o modelo será aumentar o número de amostras físicas com Kappa de referência, em condições consistentes, na posição e orientação marcadas pelo usuário. As três posições antigas ficam como ensaio de sensibilidade; novos testes de retirada e recolocação devem respeitar as marcações, sem exigir varredura espacial na rotina. O firmware não pode substituir essa informação por ajuste numérico.

Recomendação: testar primeiro o PLS SNV no supervisório com os parâmetros atuais. Depois acrescentar telemetria de aquisição e diagnóstico antecipado de I²C em uma revisão separada, com testes do protocolo e ensaios na estação, preservando os controles de porta, gaveta e carrinho.
