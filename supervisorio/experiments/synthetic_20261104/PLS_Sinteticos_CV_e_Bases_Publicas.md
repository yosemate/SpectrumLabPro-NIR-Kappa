# PLS experimental — simulação concluída em 04/11/2026

Foram gerados e exportados **1.179.648 espectros sintéticos**, distribuídos em quatro bases de teste agrupado. Foram processadas aproximadamente **110,5 milhões de entradas de treino ao longo dos ensaios**, incluindo reutilização entre configurações: isso não representa 110,5 milhões de amostras independentes.

O ensaio abrangeu PLS com 1 a 6 componentes, com/sem autoescala, reflectância, normalização pela soma, SNV, absorbância −log10 e absorbância com SNV. MSC já havia sido avaliado e apresentou inclinações inválidas em partições deste conjunto. Não foi convertido em um modelo válido artificialmente.

## Variações simuladas

O CV global observado do branco é 0,3571%; o maior CV por canal é 0,4290%. Foram simuladas perturbações globais de 1×, 3× e 10× esse CV. Além disso, foram utilizados a covariância observada entre os seis canais e três envelopes combinados:

| Envelope | Intensidade | Deslocamento de reflectância | Inclinação espectral | Ruído relativo por canal (desvio padrão) | Covariância do branco |
|---|---:|---:|---:|---:|---:|
| Leve | ±5% | ±0,002 | ±1% | 0,25% | 1× |
| Moderado | ±10% | ±0,005 | ±2% | 0,50% | 3× |
| Amplo | ±20% | ±0,010 | ±5% | 1,00% | 10× |

As combinações foram distribuídas por sequências Sobol em 15 dimensões. Elas cobrem os envelopes declarados; não abrangem todas as possibilidades físicas. Ruídos gaussianos não possuem limites rígidos nesses valores. A incerteza da média do branco foi estimada pela covariância de dez leituras dividida por dez. Isso supõe leituras intercambiáveis; a tendência de aproximadamente 0,9–1,3% observada durante a sequência do branco limita essa interpretação. Os multiplicadores maiores são testes de estresse, não medições de deriva real.

## Separação das amostras

Há quatro amostras físicas com referência laboratorial: 4,27; 4,50; 19,28; 19,95. Em cada teste, uma delas ficou totalmente fora da geração e do treino: nem seu espectro nem seu Kappa foram usados para criar as linhas sintéticas. As repetições de 4,50 pertencem à mesma amostra. O estimador recebeu apenas linhas sintéticas, cujos alvos foram herdados das outras três referências. A calibração óptica comum foi mantida como informação instrumental.

As quatro bases exportadas têm 294.912 linhas cada. **Use somente a base cujo nome exclui a amostra que será testada. Mesclar as bases e depois testar essas mesmas quatro amostras causaria vazamento.** Todas as 1.179.648 linhas foram verificadas quanto a contagem, origem, exclusão da amostra de teste, valores finitos positivos e marcação sintética; os arquivos também tiveram seus hashes conferidos.

Celulose Branqueada não entrou nesses treinos: seu Kappa 0,58 é assumido, não certificado. Nenhuma nova referência laboratorial foi inventada.

## Resultados fora do treino

| Configuração | RMSE em Kappa |
|---|---:|
| PLS de reflectância sem ampliação sintética | 6,35 |
| PLS com soma sem ampliação sintética | 5,59 |
| PLS com SNV sem ampliação sintética | 6,78 |
| Sintético amplo, reflectância, PLS 1 componente | **4,81** |
| Sintético amplo, reflectância autoescalada, PLS 1 componente | **4,82** |
| Sintético amplo, soma, PLS 3 componentes | 5,37 |

O modelo alternativo exportado usa reflectância **autoescalada**, PLS de um componente e o envelope amplo. A autoescala está incorporada aos coeficientes do JSON para compatibilidade com o carregador existente; a interface pode mostrá-lo como RAW. Ele não utiliza SNV, porque SNV apresentou desempenho inferior neste conjunto.

| Kappa de laboratório | Predição fora do treino do modelo autoescalado |
|---|---:|
| 4,27 | 5,25 |
| 4,50 | 9,63 |
| 19,28 | 22,38 |
| 19,95 | 12,46 |

As predições acima são de uma das três sequências confirmatórias; as diferenças entre sequências foram inferiores a 0,00001 Kappa. Média do RMSE: 4,81979; MAE: 4,17334. O melhor modelo sem autoescala apresentou RMSE 4,80694 e predições 5,17; 9,64; 22,41; 12,51 na mesma ordem. Portanto, a simulação melhorou o erro agregado, mas **ainda não mede adequadamente todas as quatro amostras**.

Aumentar de 4.096 para 65.536 sintéticos por amostra de origem estabilizou o melhor RMSE em aproximadamente 4,80694. O ganho por mais volume tornou-se desprezível. O número de referências químicas continua sendo quatro. Perturbar o branco e o espectro não cria informação nova sobre a relação química entre espectro e Kappa. Normalização pela soma e SNV também cancelam grande parte de uma multiplicação global comum.

Como várias configurações foram escolhidas comparando essas mesmas quatro amostras, os resultados são exploratórios e podem ser otimistas. Não há validação industrial nem teste externo independente. As referências não cobrem os valores intermediários do intervalo.

## Modelo e reversibilidade

O JSON alternativo foi ajustado com 262.144 linhas sintéticas originadas das quatro amostras após os testes agrupados. As predições sobre suas próprias amostras de origem não são validação; estão identificadas separadamente no arquivo de resultados. A equivalência numérica entre a inferência do JSON e o ajuste original foi verificada nas cinco leituras reais disponíveis, com tolerância de 1e−10.

Para experimentar, carregar `PLS_Sintetico_Autoescalado_Experimental.json` pelo botão de modelo PLS. O modelo padrão, a calibração óptica, o firmware e os executáveis existentes foram preservados. Voltar ao modelo anterior ou desativar o modo experimental reverte a experiência. Não interpretar a previsão como resultado laboratorial certificado.

## Busca de bases públicas

Não foi localizada nesta busca uma matriz aberta de espectros individuais com Kappa correspondente diretamente utilizável nos seis canais do AS7263. Foram examinados estes candidatos:

- [OpenMV Kappa-number](https://openmv.net/info/kappa-number): série simulada com uma coluna de Kappa; não oferece os seis preditores espectrais necessários. O [catálogo OpenMV](https://www.openmv.net/) também lista Kamyr como dados de processo, não espectros equivalentes.
- [Estudo BioResources sobre Acacia](https://bioresources.cnr.ncsu.edu/resources/kappa-number-prediction-of-acacia-melanoxylon-unbleached-kraft-pulps-using-nir-plsr-models-with-a-narrow-interval-of-variation/): utiliza 75 amostras e uma região selecionada de aproximadamente 1637–1838 nm, fora dos 610–860 nm deste equipamento. Não foi localizada matriz individual aberta nessa página.
- [Estudo de 2015, VNIR/NIR](https://onlinelibrary.wiley.com/doi/10.1155/2015/104609): parte da aquisição cobre nominalmente 400–2500 nm, mas não foi localizada tabela aberta dos espectros individuais pareados a Kappa. Curvas médias e tabelas de cozimento não substituem esses dados.
- [Artigo de 2024, Analytica Chimica Acta](https://www.sciencedirect.com/science/article/pii/S0003267024006962): o estudo aborda amostras de celulose e Kappa, mas a declaração de disponibilidade informa que os autores não têm permissão para compartilhar os dados.
- [Zenodo: controle de polpas kraft branqueadas](https://zenodo.org/records/21789850): há dados NIR/Raman, mas os alvos identificados são extrativos; não foi confirmado um conjunto pareado de Kappa utilizável.
- [Mendeley: dados de celulose oxidada](https://data.mendeley.com/datasets/bncy3n34v7/1): alvo de oxidação, não Kappa. Não foi usado como substituto.
- [Tese de Auburn](https://auetd.auburn.edu/handle/10415/336): descreve instrumentos e calibração; não foi localizada matriz completa de espectros individuais com referências pronta para transferência.

Dados de outros instrumentos exigiriam compatibilidade de banda, resposta óptica e transferência de calibração. Nenhuma base incompatível foi rotulada artificialmente como se tivesse sido medida pelo seu equipamento.
