# Cinematic Chronos

Projeto de ciência de dados para responder, com evidência estatística, se os filmes estão ficando mais longos ao longo do tempo. Como não analisamos todos os filmes lançados no mundo, usamos os indicados ao Oscar de Melhor Filme como uma proxy histórica, pública e rastreável para investigar essa tendência.

O projeto foi construído como um pipeline reprodutível de dados, usando arquitetura em camadas `raw`, `bronze`, `silver` e `gold`, separação clara de responsabilidades e componentes pequenos, testáveis e extensíveis. A proposta é demonstrar tanto a investigação estatística quanto decisões de engenharia esperadas em um portfólio sênior.

## Pergunta Analítica

A afirmação investigada é:

> Os filmes vêm aumentando de duração total ao longo do tempo.

Como seria impraticável coletar e validar todos os filmes produzidos globalmente em quase um século de cinema, o projeto usa os indicados ao Oscar de Melhor Filme como proxy. Esse recorte não representa o universo completo de filmes, mas oferece uma série histórica longa, reconhecida publicamente, auditável e com critérios de seleção documentados dentro da indústria cinematográfica.

Assim, a pergunta operacional do projeto é: dentro dessa proxy, existe evidência estatística de aumento da duração dos filmes ao longo do tempo? A resposta será interpretada como um sinal empírico para a hipótese mais ampla sobre filmes em geral, não como prova definitiva sobre toda a produção cinematográfica mundial.

## Hipótese Estatística

A validação será feita por inferência estatística com Regressão Linear Simples:

```text
y = beta_0 + beta_1 x + epsilon
```

Onde:

- `y`: duração do filme indicado ao Oscar de Melhor Filme, em minutos.
- `x`: ano do filme.
- `beta_0`: intercepto estimado.
- `beta_1`: coeficiente angular, interpretado como variação média de minutos por ano.
- `epsilon`: termo de erro.

O teste principal avalia o p-valor associado a `beta_1`.

- Hipótese nula, `H0`: `beta_1 = 0`, ou seja, não há evidência estatística de variação linear da duração ao longo dos anos.
- Hipótese alternativa, `H1`: `beta_1 != 0`, usando o p-valor bilateral padrão reportado por `statsmodels`.

Como a pergunta de negócio é sobre aumento, a conclusão final exige duas condições: `beta_1` positivo e p-valor menor que `alpha`. Assim, a significância indica que há variação linear detectável, e o sinal positivo do coeficiente sustenta a leitura de aumento.

Com nível de significância definido no notebook ou módulo analítico final, a decisão será:

- rejeitar `H0` se o p-valor de `beta_1` for menor que `alpha`;
- não rejeitar `H0` se o p-valor de `beta_1` for maior ou igual a `alpha`.

Importante: significância estatística não implica causalidade nem generalização automática para todos os filmes do mundo. O modelo responde se existe uma tendência linear positiva detectável na proxy analisada. A interpretação para o cinema como um todo deve ser feita como inferência indireta, com as limitações do recorte claramente declaradas.

## Fontes de Dados

O projeto usa duas fontes:

- Kaggle: dataset público `unanimad/the-oscar-award`, usado para obter a lista histórica de indicados ao Oscar de Melhor Filme, que funciona como proxy da análise.
- IMDb/TMDb: fontes consideradas para duração dos filmes. No estado atual do código, o adapter implementado é o TMDb.

A documentação e o código tratam dados brutos como artefatos de execução. O diretório `data/` não deve ser versionado; o pipeline permite reconstruir os datasets locais a partir das fontes configuradas.

## Estado Atual do Pipeline

As etapas implementadas cobrem a ingestão e a preparação da base analítica:

- `raw`: download do Kaggle em `data/raw/kaggle/oscar_awards` e manifesto append-only em `data/raw/manifest.jsonl`.
- `bronze`: filtro dos registros históricos equivalentes a Melhor Filme e escrita em Parquet.
- `gold`: enriquecimento de duração via TMDb, com cache local e controle de chamadas.
- `silver`: camada prevista para padronização analítica intermediária, como normalização de nomes, tipos e chaves de filme/ano antes da modelagem.

Com os dados locais existentes durante esta revisão, os artefatos materializados contêm:

- `bronze`: 621 registros, cobrindo anos de filme de 1927 a 2025.
- `gold`: 621 registros, todos com `runtime_minutes`, `runtime_source` e `tmdb_id` preenchidos.

Esses números são derivados dos Parquets locais e podem mudar quando o dataset Kaggle ou as regras de enriquecimento forem atualizados.

## Arquitetura

```text
cinematic_chronos/
  config/
    ingestion.json
  scripts/
    run_extract.py
    run_process_bronze.py
    run_enrich_tmdb_runtime.py
  notebooks/
    01_eda_gold_understanding.ipynb
    02_runtime_over_time_visual_analysis.ipynb
    03_statistical_inference_runtime_trend.ipynb
    04_temporal_context_decade_splines.ipynb
    05_robustness_annual_aggregation.ipynb
  src/cinematic_chronos/
    clients/
      tmdb.py
    ingestion/
      kaggle.py
      pipeline.py
    processing/
      bronze.py
      runtime_enrichment.py
    utils/
      columns.py
      env.py
    cli.py
    config.py
    models.py
    storage.py
  tests/
    test_ingestion.py
```

### Fluxo de Dados

```mermaid
flowchart LR
    Kaggle["Kaggle: Oscar awards"] --> Raw["Raw: arquivos originais"]
    Raw --> Manifest["Manifesto JSONL"]
    Raw --> Bronze["Bronze: proxy com indicados a Melhor Filme"]
    Bronze --> Gold["Gold: runtime enriquecido"]
    TMDb["TMDb API"] --> Cache["Cache local de respostas"]
    Cache --> Gold
    Gold --> EDA["EDA e visualizações"]
    Gold --> Inference["Inferência estatística"]
    Inference --> Robustness["Robustez: décadas, splines e agregação anual"]
```

## Decisões de Arquitetura

### Camadas Medallion

A separação entre `raw`, `bronze`, `silver` e `gold` evita misturar coleta, limpeza, enriquecimento e modelagem. Isso melhora rastreabilidade e permite reprocessar uma etapa sem repetir todo o pipeline.

- `raw` preserva os arquivos de origem com mínima intervenção.
- `bronze` aplica o primeiro critério de negócio: manter apenas indicados a Melhor Filme, que formam a proxy do estudo.
- `silver` fica reservada para padronização e validações analíticas antes do modelo.
- `gold` entrega a tabela enriquecida com duração, pronta para exploração e inferência.

### Parquet com Compressão ZSTD

As camadas processadas são gravadas em Parquet com compressão ZSTD. A escolha reduz tamanho em disco, preserva schema tabular e melhora leitura seletiva para análises com Pandas, DuckDB ou ferramentas analíticas modernas.

### Manifesto de Ingestão

Cada execução de extract registra metadados em JSON Lines, incluindo origem, destino, status, bytes e timestamp. Esse padrão torna a ingestão auditável sem depender de logs efêmeros.

### Cache de TMDb

O enriquecimento de runtime usa cache local em `data/raw/tmdb/runtime_cache`. Isso evita chamadas repetidas para a API, reduz custo operacional, respeita limites de requisição e torna execuções posteriores mais rápidas.

### Enriquecimento Incremental

A etapa TMDb consulta apenas filmes com `runtime_minutes` ausente. Essa decisão reduz chamadas externas e permite combinar fontes futuras, como IMDb, sem sobrescrever informações já resolvidas.

### Configuração Externa

Diretórios, dataset Kaggle, variáveis de ambiente e parâmetros TMDb ficam em `config/ingestion.json`. O código não precisa mudar para alterar paths, cache, idioma ou nome da variável de segredo.

## SOLID na Implementação

O projeto aplica princípios SOLID de forma pragmática:

- Responsabilidade única: `KaggleDatasetDownloader` baixa datasets, `LocalRawStore` persiste arquivos/metadados, `TmdbRuntimeClient` conversa com TMDb, `process_bronze` transforma Oscar bruto em camada bronze.
- Aberto/fechado: novas fontes podem ser adicionadas como novos adapters de ingestão sem alterar a lógica de armazenamento local.
- Substituição de dependências: o cliente TMDb aceita uma `requests.Session` opcional, permitindo testes com doubles sem chamadas reais.
- Segregação de interfaces: os componentes expostos são pequenos e orientados a uma tarefa específica.
- Inversão de dependência: scripts e CLI orquestram componentes; regras de negócio e clientes externos ficam isolados em módulos reutilizáveis.

## Como Executar

Execute os comandos a partir da raiz do repositório.

### 1. Preparar ambiente

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

Para usar Kaggle, configure `KAGGLE_USERNAME` e `KAGGLE_KEY` ou `%USERPROFILE%\.kaggle\kaggle.json`.

Para usar TMDb:

```powershell
Copy-Item cinematic_chronos\.env.example cinematic_chronos\.env
```

Depois preencha `TMDB_API_KEY` em `cinematic_chronos\.env`.

### 2. Baixar dados brutos

```powershell
.\.venv\Scripts\python.exe cinematic_chronos\scripts\run_extract.py
```

Para validar destinos sem chamar fontes externas:

```powershell
.\.venv\Scripts\python.exe cinematic_chronos\scripts\run_extract.py --dry-run
```

Para forçar atualização:

```powershell
.\.venv\Scripts\python.exe cinematic_chronos\scripts\run_extract.py --force
```

### 3. Gerar bronze

```powershell
.\.venv\Scripts\python.exe cinematic_chronos\scripts\run_process_bronze.py
```

Ou via CLI:

```powershell
.\.venv\Scripts\python.exe cinematic_chronos\scripts\run_extract.py process-bronze
```

### 4. Enriquecer duração com TMDb

Validação sem chamadas de API:

```powershell
.\.venv\Scripts\python.exe cinematic_chronos\scripts\run_enrich_tmdb_runtime.py --dry-run
```

Execução efetiva:

```powershell
.\.venv\Scripts\python.exe cinematic_chronos\scripts\run_enrich_tmdb_runtime.py
```

Ou via CLI:

```powershell
.\.venv\Scripts\python.exe cinematic_chronos\scripts\run_extract.py enrich-tmdb-runtime
```

### 5. Executar notebooks analíticos

Os notebooks consomem a camada `gold` em `cinematic_chronos/data/gold/oscar_best_picture_nominees_runtime.parquet`.

Abra os notebooks em um ambiente Jupyter compatível, como VS Code, JupyterLab ou Notebook. Caso queira usar JupyterLab a partir deste ambiente virtual, instale a interface antes:

```powershell
.\.venv\Scripts\python.exe -m pip install jupyterlab
.\.venv\Scripts\python.exe -m jupyter lab cinematic_chronos\notebooks
```

Ordem recomendada:

1. `01_eda_gold_understanding.ipynb`: entendimento completo da base gold, schema, completude, distribuição e qualidade.
2. `02_runtime_over_time_visual_analysis.ipynb`: visualizações temporais da duração dos filmes.
3. `03_statistical_inference_runtime_trend.ipynb`: regressão linear simples para responder à pergunta central do projeto.
4. `04_temporal_context_decade_splines.ipynb`: modelos por década, efeitos de período e splines para avaliar não linearidade.
5. `05_robustness_annual_aggregation.ipynb`: regressão robusta, agregação anual, erros robustos e influência de outliers.

## Qualidade e Testes

Os testes cobrem configuração, armazenamento local, dry-run de Kaggle, filtro de Melhor Filme, escrita Parquet da bronze, enriquecimento TMDb, leitura de segredo via `.env`, cache e fallbacks de busca.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s cinematic_chronos\tests
```

## Notebooks Analíticos

A etapa analítica consome `data/gold/oscar_best_picture_nominees_runtime.parquet` e está organizada em cinco notebooks complementares:

- `01_eda_gold_understanding.ipynb`: valida schema, completude, granularidade, duplicidades, distribuição geral de durações e diferenças por década e por status de vencedor.
- `02_runtime_over_time_visual_analysis.ipynb`: mostra graficamente o comportamento da duração ao longo do tempo, com pontos individuais, médias anuais, medianas, médias móveis, faixas interquartis e heatmap por faixas de duração.
- `03_statistical_inference_runtime_trend.ipynb`: ajusta a Regressão Linear Simples `runtime_minutes ~ year_film`, avalia `beta_1`, p-valor, intervalo de confiança, `R²` e diagnósticos de resíduos.
- `04_temporal_context_decade_splines.ipynb`: testa sensibilidade temporal com modelos por década, efeitos fixos de década, interação década-tempo e spline cúbico.
- `05_robustness_annual_aggregation.ipynb`: verifica se a conclusão permanece usando média anual, mediana anual, WLS, regressões robustas Huber/Tukey, erros padrão robustos e Cook's distance.

O notebook inferencial principal executa o seguinte modelo conceitual:

Exemplo conceitual:

```python
import pandas as pd
import statsmodels.api as sm

data = pd.read_parquet("cinematic_chronos/data/gold/oscar_best_picture_nominees_runtime.parquet")
model_data = data[["year_film", "runtime_minutes"]].dropna()

X = sm.add_constant(model_data["year_film"])
y = model_data["runtime_minutes"]

model = sm.OLS(y, X).fit()
print(model.summary())
```

O resultado central para a pergunta operacional será o sinal e o p-valor de `year_film`. A conclusão deve separar claramente o achado na proxy dos indicados ao Oscar e a interpretação mais ampla sobre filmes em geral.

## Resultados

Com a base `gold` local atual, a análise considera 621 filmes indicados ao Oscar de Melhor Filme, cobrindo anos de filme de 1927 a 2025. Todos os registros usados na inferência têm `year_film` e `runtime_minutes` preenchidos.

### Resultado Principal

O modelo de Regressão Linear Simples estima:

```text
runtime_minutes = beta_0 + beta_1 * year_film + epsilon
```

Resultado para `beta_1`:

- coeficiente estimado: `0.2402` minuto por ano;
- p-valor: `5.14e-12`;
- intervalo de confiança de 95%: `[0.1732, 0.3072]`;
- `R²`: `0.0741`;
- mudança estimada de 1927 a 2025: aproximadamente `23.5` minutos.

Com `alpha = 0.05`, rejeitamos `H0: beta_1 = 0`. Como o coeficiente é positivo, a evidência estatística sustenta que, dentro da proxy dos indicados ao Oscar de Melhor Filme, a duração média dos filmes aumentou ao longo do tempo.

### Leitura Sênior

O resultado é estatisticamente forte, mas o tamanho explicativo do modelo é moderado. O `R²` de `0.0741` indica que o ano do filme explica uma parcela pequena da variação individual de duração. Isso é esperado: duração de filme depende de gênero, estúdio, diretor, tecnologia, regras industriais, preferências de audiência, orçamento, estratégia de distribuição e outros fatores que não estão no modelo.

A pergunta do projeto, porém, não exige explicar toda a variação de duração. Ela exige testar se existe uma tendência temporal positiva detectável. Nesse ponto, o modelo é consistente: o coeficiente é positivo, o intervalo de confiança não cruza zero e o p-valor é muito inferior a `0.05`.

A estimativa de `0.2402` minuto por ano deve ser lida como tendência média histórica. Em um único ano, o efeito parece pequeno. Ao longo de quase um século, ele acumula aproximadamente `23.5` minutos, magnitude material para a experiência de assistir a um filme.

### Robustez

A conclusão não depende apenas do OLS em nível de filme. As análises complementares mantêm coeficiente positivo e significância estatística:

| Especificação | `beta_1` | p-valor |
| --- | ---: | ---: |
| OLS por filme | `0.2402` | `5.14e-12` |
| OLS por média anual | `0.2198` | `7.50e-05` |
| OLS por mediana anual | `0.2133` | `2.32e-04` |
| WLS por média anual | `0.2402` | `1.33e-06` |
| Regressão robusta Huber | `0.2617` | `1.32e-18` |
| Regressão robusta Tukey | `0.2665` | `3.29e-19` |

Essa consistência reduz a chance de que a conclusão seja artefato de anos com mais indicados, de filmes extremos ou da escolha específica de um OLS simples.

Os modelos temporais também mostram que representações mais flexíveis capturam estrutura adicional:

| Modelo | AIC | BIC | `R²` |
| --- | ---: | ---: | ---: |
| Linear simples | `5836.28` | `5845.15` | `0.0741` |
| Linear + efeitos de década | `5786.34` | `5839.52` | `0.1727` |
| Interação década-tempo | `5766.00` | `5863.49` | `0.2248` |
| Spline cúbico `df=5` | `5782.34` | `5808.92` | `0.1620` |

O spline e os controles por década melhoram o ajuste, sugerindo que a evolução não é perfeitamente descrita por uma reta única. Ainda assim, eles não invalidam a leitura central: a direção histórica estimada é positiva.

### Conclusão Executiva

Na proxy analisada, há evidência estatística robusta de que os filmes indicados ao Oscar de Melhor Filme ficaram mais longos ao longo do tempo. A melhor leitura não é "todo filme está ficando mais longo", mas sim: em uma série histórica pública, auditável e relevante da indústria cinematográfica, há um sinal positivo, estatisticamente significativo e robusto a especificações alternativas.

Essa conclusão é forte como evidência empírica dentro do recorte estudado. Ela não estabelece causalidade e não deve ser generalizada automaticamente para todo o universo de filmes sem uma amostra mais ampla.

## Limitações

- O recorte de indicados ao Oscar é uma proxy e não representa todos os filmes lançados no mundo.
- Mudanças históricas nas regras da categoria Melhor Filme podem afetar a composição da amostra.
- O enriquecimento TMDb depende de correspondência por título e ano; o cache e os fallbacks reduzem, mas não eliminam, risco de match incorreto.
- A regressão linear simples testa tendência linear média, mas pode não capturar quebras estruturais, mudanças por década ou efeitos de outliers.

## Próximos Passos

- Implementar a camada `silver` com schema analítico canônico.
- Adicionar validações automatizadas de qualidade de dados para a camada `gold`.
- Evoluir a análise para modelos com covariáveis adicionais, como gênero, estúdio, idioma, orçamento ou receita, caso novas fontes sejam incorporadas.
- Publicar uma versão executada dos notebooks com gráficos e tabelas renderizados para leitura fora do ambiente local.
