# Decisões

| #     | Decisão                                                                                                                             | Status   |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------- | -------- |
| D-001 | `.rvt` fora do git (215 MB > limite de 100 MB do GitHub). Repo guarda scripts, dados processados e docs.                            | Proposta |
| D-002 | Mapas num arquivo próprio `TCC-MAPAS.rvt`, vinculando o terreno por coordenadas compartilhadas — o `TERRENO` não é editado.         | Proposta |
| D-003 | Fonte do entorno (vias, quadras, lotes, edificações): base da Prefeitura (MUBDG) se houver acesso; senão OpenStreetMap.             | Aberta   |
| D-004 | Usos do solo: tabela `lote → uso` semeada do mapa do Canva e validada pela Jacqueline.                                              | Aberta   |
| D-005 | Redes de esgoto/água/energia: sem base vetorial pública confirmada — redesenhar sobre a imagem georreferenciada ou pedir à Saneago. | Aberta   |
| D-006 | Raio do recorte: 300 m (estimado do Canva).                                                                                         | Aberta   |
| D-007 | Automações de pisos/paredes/portas/pergolado (`~/Projects/ctj-tcc-revit`, sem commits) migram para `automacao/` deste repo.         | Aberta   |
| D-008 | O terreno **não está georreferenciado** (inventário de 2026-10-08: ponto de levantamento em 0,0,0, localização padrão "Brasília", norte verdadeiro 0°). Mapas e lotes usam as coordenadas internas do modelo, que são as mesmas do DWG BASE REVIT. Georreferenciar só se formos importar dados externos (OSM/Prefeitura). | Registrada |
| D-009 | Lotes = subdivisões `.LOTE` do terreno (`.RUA`), criadas por script a partir do DWG `Arquivo Completo- BASE REVIT.dwg (2)` (#2996417 — a cópia #2899098 está deslocada ~16 km), camadas `Lot$0$Lot` + `Qdr$0$Qdr`. Quadras = anéis `CALÇADA 2`; o lote vai no furo. Polígono que cai num `.LOTE` existente (lotes manuais, terreno do CTJ #2992520) não é recriado. Marca `TCC-AUTO-LOTE`. | Em teste (piloto) |
