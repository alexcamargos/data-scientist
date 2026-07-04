# Cinematic Chronos

Projeto de dados para analisar a trajetória temporal de filmes indicados ao Oscar.

## Objetivo

Este projeto investiga se a duração total dos filmes indicados ao Oscar de Melhor Filme aumenta ao longo do tempo. A arquitetura segue o padrão de camadas `bronze`, `silver` e `gold`, começando pela separação dos indicados a Melhor Filme na camada `bronze`.

## Camada implementada: Extract

Esta etapa baixa e armazena dados brutos em batch, mantendo os arquivos originais sem transformação dentro de `data/raw`:

- Kaggle: dataset público `unanimad/the-oscar-award`, salvo em `data/raw/kaggle/oscar_awards`.
- Manifesto: cada execução registrada em `data/raw/manifest.jsonl` com origem, destino, status, bytes e hash quando disponível.

O diretório `data/` já é ignorado pelo `.gitignore` do repositório principal, então os arquivos baixados não entram no versionamento.

## Camada implementada: Bronze

Esta etapa lê o CSV bruto baixado do Kaggle e gera `data/bronze/oscar_best_picture_nominees.parquet`, mantendo apenas registros cuja categoria representa indicados a Melhor Filme. A camada `bronze` usa Parquet, formato colunar padrão em pipelines analíticos modernos, com compressão ZSTD:

- `Best Picture`
- `Outstanding Picture`
- `Outstanding Production`
- variações históricas equivalentes configuradas no código

## Enriquecimento via TMDb

O runtime é preenchido na camada `gold` por uma etapa de enriquecimento via API do TMDb. Para controlar custo e rate limiting, a etapa só consulta a API para filmes cujo campo `runtime_minutes` está ausente ou nulo, ou seja, os indicados ao Oscar que não receberam runtime em uma etapa anterior de match com IMDb. As respostas ficam em cache local em `data/raw/tmdb/runtime_cache`, evitando chamadas repetidas para o mesmo título/ano.

## Uso com a venv existente

Execute a partir da raiz do repositório:

```powershell
.\.venv\Scripts\python.exe cinematic_chronos\scripts\run_extract.py
```

Para verificar a resolução dos destinos sem baixar:

```powershell
.\.venv\Scripts\python.exe cinematic_chronos\scripts\run_extract.py --dry-run
```

Para atualizar arquivos já existentes:

```powershell
.\.venv\Scripts\python.exe cinematic_chronos\scripts\run_extract.py --force
```

Para gerar a camada `bronze` após o download do Kaggle:

```powershell
.\.venv\Scripts\python.exe cinematic_chronos\scripts\run_process_bronze.py
```

Também é possível usar o subcomando:

```powershell
.\.venv\Scripts\python.exe cinematic_chronos\scripts\run_extract.py process-bronze
```

Para conferir quantos filmes exigiriam TMDb sem chamar a API:

```powershell
.\.venv\Scripts\python.exe cinematic_chronos\scripts\run_enrich_tmdb_runtime.py --dry-run
```

Para enriquecer runtime com TMDb:

```powershell
Copy-Item cinematic_chronos\.env.example cinematic_chronos\.env
# edite cinematic_chronos\.env e preencha TMDB_API_KEY
.\.venv\Scripts\python.exe cinematic_chronos\scripts\run_enrich_tmdb_runtime.py
```

Também é possível usar o subcomando:

```powershell
.\.venv\Scripts\python.exe cinematic_chronos\scripts\run_extract.py enrich-tmdb-runtime
```

## Kaggle

A ingestão do Kaggle depende do cliente oficial e de credenciais locais. Instale na venv principal e configure `KAGGLE_USERNAME`/`KAGGLE_KEY` ou `%USERPROFILE%\.kaggle\kaggle.json`:

```powershell
.\.venv\Scripts\python.exe -m pip install kaggle
.\.venv\Scripts\python.exe cinematic_chronos\scripts\run_extract.py --source kaggle
```

O dataset pode ser alterado em `config/ingestion.json`, no campo `kaggle.dataset_slug`.

## Estrutura

```text
cinematic_chronos/
  config/ingestion.json
  scripts/run_extract.py
  scripts/run_enrich_tmdb_runtime.py
  scripts/run_process_bronze.py
  src/cinematic_chronos/cli.py
  src/cinematic_chronos/config.py
  src/cinematic_chronos/models.py
  src/cinematic_chronos/storage.py
  src/cinematic_chronos/clients/tmdb.py
  src/cinematic_chronos/ingestion/
  src/cinematic_chronos/processing/
  src/cinematic_chronos/utils/
  tests/test_ingestion.py
```

## Testes

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s cinematic_chronos\tests
```
