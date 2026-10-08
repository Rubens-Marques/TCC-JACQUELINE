# Modelos Revit

Os `.rvt` **não vão para o git** (o do terreno tem 215 MB; o GitHub recusa arquivos > 100 MB).
Eles ficam na pasta de trabalho do Revit no Windows; aqui registramos nomes, versão e vínculos.

| Arquivo                      | Versão     | Papel                                                                             |
| ---------------------------- | ---------- | --------------------------------------------------------------------------------- |
| `TERRENO - JD IPE-TCC.rvt`   | Revit 2026 | Superfície topográfica do lote. Fonte das coordenadas compartilhadas. Não editar. |
| `CTJ-TCC-MODELAGEM.rvt`      | Revit 2026 | Projeto do CTJ (vincula o terreno).                                               |
| `TCC-MAPAS.rvt` _(proposto)_ | Revit 2026 | Mapas de análise. Vincula o terreno por coordenadas compartilhadas.               |

Saídas de inventário (`inventario_*.json`) podem ser copiadas para esta pasta e versionadas
se forem renomeadas (o padrão `inventario_*.json` é ignorado para não subir sem querer).
