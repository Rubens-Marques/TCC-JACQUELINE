# TCC — Centro de Transformação Juvenil (CTJ)

TCC II de Jacqueline Alencar Marques · PUC Goiás, Escola Politécnica e de Artes · 2026.2
Orientadora: Camilla Pompeo

Este repositório organiza a parte **gráfica e de modelagem** do TCC: os mapas de análise
do terreno (seção 4.5 do caderno), a setorização e as automações (Dynamo / pyRevit) que
sobem a modelagem no Revit 2026.

## Estrutura

```
docs/            Contexto do projeto, especificação dos mapas, decisões
referencias/     Material de origem (Canva, fotos, PDFs) — só leitura
dados/
  brutos/        GIS baixado (OSM, Prefeitura, etc.) — fora do git
  processados/   Geometria recortada e classificada, pronta para o Revit
revit/           Onde ficam os .rvt (fora do git) e como estão vinculados
automacao/
  pyrevit/       Extensão pyRevit (botões dentro do Revit)
  dynamo/        Grafos .dyn
  scripts/       Python que roda fora do Revit (preparo de dados)
tests/           Checagens rodadas no Mac antes de levar ao Revit
```

## Fluxo

1. **Inventário** — no Revit 2026, com o `TERRENO - JD IPE-TCC.rvt` aberto:
   `Gerenciar` → `Dynamo` → abrir `automacao/dynamo/TCC_Inventario.dyn` → **Run**.
   Somente leitura. Salva `inventario_<arquivo>.json` ao lado do `.rvt` (geolocalização,
   coordenadas compartilhadas, topografia, DWGs e camadas, vistas, tipos).
2. **Lotes** — `automacao/dynamo/TCC_Lotes.dyn`, no mesmo arquivo do terreno. Lê as
   camadas de lote/quadra do DWG `Arquivo Completo- BASE REVIT`, fecha os polígonos e cria
   cada lote como subdivisão da quadra (Toposolid) onde ele cai.
   - `Executar = False` → simulação: lista camadas, quantos lotes, em quais quadras.
   - `Executar = True` com `"limite": 10` → piloto numa quadra só. Conferir em 3D.
   - `"limite": 0` → todos. Reexecutar apaga só os lotes marcados `TCC-AUTO-LOTE`.
3. **Dados** — baixar e recortar o entorno (vias, quadras, lotes, edificações, APP)
   em `dados/processados/`, nas mesmas coordenadas do terreno.
4. **Mapas no Revit** — script cria as vistas, regiões preenchidas, estilos de
   linha, legendas e a prancha de cada mapa (ver `docs/mapas.md`).
5. **Setorização e paredes** — áreas do projeto → pisos e paredes via Dynamo/pyRevit.

O Revit roda no Windows (Revit 2026). Este Mac só prepara dados e scripts.

## Testes

```bash
python3 automacao/scripts/build_dyn.py   # após mudar qualquer script
python3 -m unittest discover -s tests -v
```

Os `.dyn` têm o código Python embutido (não dependem de caminho no Windows). Feche a aba
antiga do Dynamo antes de abrir uma versão nova do grafo.
