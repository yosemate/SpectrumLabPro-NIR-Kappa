# SpectrumLinux — PLS experimental com SNV

Atualização local de 04/11/2026. O modo experimental inicia desligado.

## Usar na estação isolada

1. Feche a versão anterior e execute `INICIAR_EXPERIMENTAL.sh` nesta pasta. Esse iniciador executa o código atualizado usando o ambiente Linux existente; o executável antigo em `dist` não foi substituído.
2. Faça o referenciamento óptico branco/escuro pelo procedimento existente. Não altere ganho, integração, LED, geometria ou apresentação da amostra para usar o modelo atual.
3. Encaixe a amostra na posição marcada, respeitando o lado de entrada no berço. Use as cinco aquisições estáticas do fluxo atual, sem deslocar a amostra. No cartão de resultado, selecione **PLS experimental — comparação**. O modelo SNV treinado já está disponível. O resultado demonstrativo antigo permanece separado.
4. Para comparar com o PLS sem normalização, use **Carregar modelo PLS experimental** e selecione `experiments/chemometrics/model_raw.json`. Para voltar ao SNV, selecione `model_snv.json`.
5. O cartão PLS também mostra o desvio padrão entre as aquisições estáticas, identificado como repetibilidade. **Exportar comparação PLS (JSON)** registra resultado, modelo, métricas, espectro, referência óptica e metadados do novo firmware. Os PDFs/CSVs/histórico existentes continuam a registrar o método demonstrativo; não são laudos PLS.
6. Desative o seletor para voltar à operação anterior. Qualquer falha de aquisição invalida também a comparação PLS.

## Modelo treinado e dados

PLS1, um componente fixado previamente, sem escalonamento adicional dos canais. SNV verdadeiro: subtrair a média dos seis canais e dividir pelo desvio padrão amostral (divisor 5). Os coeficientes são exportados em JSON; previsão usa apenas NumPy, sem carregar pickle nem exigir scikit-learn na estação.

Referências fornecidas pelo usuário: Kappa 4,27; 4,50; 19,28; 19,95. A associação foi conferida pelos identificadores dos PDFs com o CSV histórico. Os valores de referência provêm dos nomes de arquivo fornecidos pelo usuário; os PDFs são relatórios do protótipo, não certificados laboratoriais independentes.

O procedimento de rotina definido pelo usuário é sempre a mesma posição e orientação, com marcações no berço/amostra. As três posições históricas de 19,28 são um ensaio de sensibilidade ao posicionamento e uma única amostra física; não há exigência de reposicionamento no uso normal. Os sete registros representam cinco amostras, sendo quatro referências de treino e uma exploratória. As cinco aquisições estáticas resumidas em cada registro não são cinco amostras independentes.

**Eldorado 0,58: PRESUMIDO. Excluído do treino, da seleção e de todas as métricas.** O modelo SNV treinado prevê aproximadamente 7,47 para esse espectro; não houve ajuste para forçar a previsão a 0,58. Não se pode pontuar esse resultado contra uma referência presumida.

As posições 2 e 3 de 19,28 foram importadas da reflectância percentual arredondada a 0,01 nos PDFs. Os outros cinco registros usam a precisão do CSV. Dois registros sem associação de referência foram excluídos. `provenance.json` contém hashes SHA-256 dos originais, IDs excluídos e limitações de origem. Nenhum arquivo original foi alterado.

## Validação por amostra física

Leave-one-sample-out: treinar com três amostras e prever todas as posições da quarta, repetindo quatro vezes. Transformações ajustáveis usam somente o treino. O MSC usa a média dos espectros representativos das amostras de treino como referência. Primeiro se agregam aquisições por posição e depois posições por amostra, dando o mesmo peso a cada amostra física.

| Método PLS | RMSE agrupado | MAE | Viés previsão − referência | R² | Amostras |
|---|---:|---:|---:|---:|---:|
| Reflectâncias sem normalização adicional | 6,551 | 6,006 | 1,271 | 0,261 | 4 |
| SNV | 2,154 | 1,844 | 0,184 | 0,920 | 4 |
| MSC | indisponível | — | — | — | — |
| Referência trivial: média do treino em cada divisão | 10,159 | 10,153 | 0,000 | −0,778 | 4 |

MSC foi implementado e testado com correções afins conhecidas. Na validação real houve inclinação negativa entre um espectro e a referência do treino; o programa rejeita essa correção e não publica uma métrica parcial como se a avaliação estivesse completa.

| Kappa fornecido | Média das previsões do modelo SNV ajustado com todas as referências (treino) | Previsão SNV com essa amostra inteiramente fora do treino |
|---|---:|---:|
| 4,27 | 2,951 | 2,308 |
| 4,50 | 6,214 | 8,051 |
| 19,28 | 18,558 | 17,922 |
| 19,95 | 20,278 | 20,455 |

Na amostra 19,28 inteiramente fora do treino, a amplitude entre posições caiu de 8,771 no PLS bruto para 2,664 com SNV. Isso não remove toda a sensibilidade ao posicionamento.

SNV foi mantido para o ensaio por apresentar o menor erro observado entre os métodos avaliados. A comparação que levou a essa escolha não constitui validação independente do método escolhido. Quatro amostras em dois intervalos de Kappa são insuficientes para demonstrar desempenho industrial, interpolação no intervalo intermediário ou generalização para novos lotes/condições. O maior erro absoluto SNV fora do treino foi 3,551. Nenhuma previsão é cortada artificialmente para coincidir com o laboratório; extrapolações do intervalo de Kappa de treino são sinalizadas. Não há detector validado de domínio espectral nem incerteza de previsão validada.

Não foram aplicadas derivadas ou suavização sobre os seis canais espaçados. A normalização pela soma permanece explicitamente disponível nos cálculos antigos; não é chamada de SNV no código novo.

## Reproduzir

Treino/comparação requer o ambiente de teste com `requirements-experimental.txt` (scikit-learn 1.9.1), além das dependências existentes. A estação precisa somente das dependências atuais para prever.

```bash
python experiments/chemometrics/import_local.py /home/yosemate/Documentos/Laudos experiments/chemometrics
python experimental_chemometrics.py experiments/chemometrics/samples.csv --method snv --output experiments/chemometrics/model_snv.json
python -m pytest tests -q
```

`validation.json` contém as divisões e métricas, e `fit_diagnostics.json` separa ajuste de treino e exploração da Eldorado. `samples.csv` é a tabela normalizada de entrada com identidade física, posição, proveniência e estado da referência. Entrada espectral sempre em fração relativa, na ordem 610, 680, 730, 760, 810, 860 nm.

Implementação PLS: [documentação oficial do scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.cross_decomposition.PLSRegression.html).

## Reversibilidade e limites

Branch local: `experimental/chemometrics-snv-20261104`. A branch `local-original` guarda o código anterior. O instalador também salva cópias dos dois arquivos substituídos em uma pasta de backup no projeto. Desligar o seletor basta para remover a comparação do fluxo de uso; para restaurar o código, com o aplicativo fechado, volte à branch `local-original`.

A revisão de aquisição PLS_ACQ_1 atualiza o firmware e a rastreabilidade do supervisório; consulte `ATUALIZACAO_FIRMWARE_PLS.md`. Controles de motores, arquivos de calibração óptica, bancos de leituras e executável anterior foram preservados. Nenhum envio ao GitHub e nenhuma gravação no ESP32 foram realizados. Testes com comunicação simulada e dados temporários: **34 passaram e 15 subtestes passaram**. Ainda falta o ensaio físico na estação com novas amostras de referência independentes.
