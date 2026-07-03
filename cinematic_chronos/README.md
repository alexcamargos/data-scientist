# Cinematic Chronos

Projeto de dados para analisar a trajetória temporal de filmes indicados ao Oscar.

## Camada implementada: Extract

Esta etapa baixa e armazena dados brutos em batch, mantendo os arquivos originais sem transformação dentro de `data/raw`:

- Kaggle: dataset público `unanimad/the-oscar-award`, salvo em `data/raw/kaggle/oscar_awards`.
- Manifesto: cada execução registrada em `data/raw/manifest.jsonl` com origem, destino, status, bytes e hash quando disponível.

O diretório `data/` já é ignorado pelo `.gitignore` do repositório principal, então os arquivos baixados não entram no versionamento.

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
  src/cinematic_chronos/ingestion.py
  tests/test_ingestion.py
```

## Testes

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s cinematic_chronos\tests
```
