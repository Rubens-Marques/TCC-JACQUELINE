# Especificação dos mapas de análise (seção 4.5)

Origem: caderno teórico, págs. 35–36 (`referencias/canva/`). Todos os mapas são refeitos
no Revit sobre o **mesmo recorte circular** centrado no terreno, na mesma escala e com o
mesmo norte, para ficarem sobrepostos.

## Padrão comum

| Item                   | Valor proposto                                               | Observação                                            |
| ---------------------- | ------------------------------------------------------------ | ----------------------------------------------------- |
| Recorte                | círculo, raio **300 m** a partir do centro do lote           | estimado das imagens do Canva (~250–300 m); confirmar |
| Escala da vista        | 1:5000 (prancha A3)                                          |                                                       |
| Coordenadas            | compartilhadas do `TERRENO - JD IPE-TCC.rvt`                 | o inventário confirma                                 |
| Norte                  | norte verdadeiro na vista                                    |                                                       |
| Área escolhida         | região preenchida `#FF9700` em todos os mapas                |                                                       |
| Fundo                  | quadras `#F2F2F2`, vias brancas, contorno de lote cinza fino | igual ao Canva                                        |
| Legenda                | vista de Legenda do Revit, uma por mapa                      |                                                       |
| Escala gráfica + norte | anotações do Revit                                           |                                                       |

Cores amostradas das legendas do Canva; as de linha são aproximadas (antialiasing).

## M1 — Mapa viário

| Camada                                          | Elemento Revit                  | Estilo                      |
| ----------------------------------------------- | ------------------------------- | --------------------------- |
| Vias arteriais (Av. Goiás Norte, Av. Nerópolis) | Linha de detalhe                | tracejada `#E65C3E`, grossa |
| Vias coletoras                                  | Linha de detalhe                | tracejada `#F7A23B`         |
| Vias locais                                     | Linha de detalhe                | contínua `#F9CB42`          |
| Pontos de ônibus / estações BRT                 | Componente de detalhe (símbolo) |                             |
| Nomes das avenidas                              | Texto ao longo da via           |                             |

Fonte: eixos de via (Prefeitura/MUBDG ou OpenStreetMap) + hierarquia viária do Plano Diretor.

## M2 — Mapa de usos

Região preenchida por **lote**: Residencial `#E2CFC9` · Misto `#E65C3E` · Serviço `#017BD1` ·
Comercial `#F9CB42` · Área verde `#C6DA92` · Vazio (sem preenchimento, contorno).

Fonte: polígonos de lote + tabela `dados/processados/usos_lotes.csv` (lote → uso),
semeada a partir do mapa do Canva e validada pela Jacqueline.

## M3 — Cheios e vazios

Edificações (projeção) `#2C2C2A` sobre fundo branco; área escolhida em laranja.
Fonte: footprints de edificações.

## M4 — Infraestrutura

| Camada                | Estilo                       |
| --------------------- | ---------------------------- |
| Esgoto                | tracejado `#A01F1F` (aprox.) |
| Abastecimento de água | tracejado `#1E9BE0` (aprox.) |
| Energia               | contínuo `#B98CF0` (aprox.)  |
| APP                   | preenchida `#C6DA92`         |

Fonte: redes da Saneago/Equatorial — **não há base vetorial pública confirmada**; ver decisões.

## M5 — Topografia e recursos naturais

- Curvas de nível a cada 5 m com rótulo (700…735), cor `#9E2A2A` (aprox.).
- APP preenchida `#C6DA92`.
- Linhas de corte AA e BB.
- Trajetória solar (nascente leste → poente oeste).

Fonte: no lote, a superfície topográfica do próprio `TERRENO.rvt` (curvas nativas do
Revit); no entorno, curvas da base municipal.

## M6 — Volumetria 3D do entorno

Massas das edificações (1–2 pavimentos, 3 m por pavimento) sobre o terreno, vista 3D
isométrica, estilo sombreado monocromático (como no Canva).

## Critérios de aceite

| #   | Critério                                                                        | Status |
| --- | ------------------------------------------------------------------------------- | ------ |
| A1  | Inventário do terreno rodado e JSON salvo em `revit/`                           | FAIL   |
| A2  | Fonte de dados de cada camada decidida (decisões D-002..D-004)                  | FAIL   |
| A3  | `dados/processados/` com camadas recortadas no raio, nas coordenadas do terreno | FAIL   |
| A4  | M1–M5 gerados no Revit por script, sobrepostos ao terreno                       | FAIL   |
| A5  | M6 gerado como massas 3D                                                        | FAIL   |
| A6  | Prancha A3 com os 6 mapas, legendas, norte e escala                             | FAIL   |
