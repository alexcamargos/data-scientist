# Messi six-sigma

Notebook para replicar e auditar o claim viral de que Lionel Messi estaria
aproximadamente "six standard deviations above the average" em gols + assistencias
por 90 minutos.

O notebook faz duas coisas:

- replica um cenario que chega perto de 6 sigma usando dados de atacantes das
  ligas Big 5 agregados por jogador;
- mostra uma analise de sensibilidade, porque o z-score muda bastante quando a
  unidade passa a ser temporada-jogador, quando mudamos o filtro de posicao ou
  quando alteramos o minimo de minutos.

## Como usar

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\messi-six-sigma\requirements.txt
```

Abra o notebook:

```powershell
jupyter lab .\messi-six-sigma\messi_six_sigma_replicacao.ipynb
```

Se estiver usando VS Code ou outro ambiente com suporte a notebooks, basta abrir
o arquivo `.ipynb` diretamente.

## Fonte dos dados

O notebook usa o arquivo publico `big5_player_standard.rds` do repositorio
`worldfootballR_data`, que armazena dados pre-coletados do FBref para as ligas
Big 5.

- Repositorio: https://github.com/JaseZiv/worldfootballR_data
- Arquivo usado: https://raw.githubusercontent.com/JaseZiv/worldfootballR_data/master/data/fb_big5_advanced_season_stats/big5_player_standard.rds

Ao executar, o notebook baixa o arquivo para `data/raw/` e gera uma tabela
derivada em `data/derived/`.
