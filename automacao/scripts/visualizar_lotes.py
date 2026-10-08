"""Desenha o JSON de diagnóstico do TCC_Lotes (lotes_<arquivo>.json) num SVG, no Mac.

Sólidos topográficos preenchidos por tipo; polígonos do DWG contornados pelo destino
(lote aceito, fora das quadras, área pequena/grande). Só biblioteca padrão.

    python3 automacao/scripts/visualizar_lotes.py lotes_TERRENO.json saida.svg
"""

import json
import sys

CORES_TIPO = ["#c9c3b8", "#9fc7e8", "#f2c879", "#b6d98f", "#e8a3a3", "#c7b3e6"]
CORES_STATUS = {
    "lote": "#1a7f37",
    "fora_das_quadras": "#d1242f",
    "area_pequena": "#8c959f",
    "area_grande": "#8250df",
}
LARGURA = 1600


def _caminho(poligono, tx):
    pontos = " L ".join("%.2f %.2f" % tx(x, y) for x, y in poligono)
    return "M %s Z" % pontos


def desenhar(dados):
    solidos = dados["solidos"]
    poligonos = dados["poligonos_dwg"]
    xs = [x for s in solidos for p in s["poligonos"] for x, _ in p] + [
        x for r in poligonos for x, _ in r["poligono"]
    ]
    ys = [y for s in solidos for p in s["poligonos"] for _, y in p] + [
        y for r in poligonos for _, y in r["poligono"]
    ]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    escala = LARGURA / float(x1 - x0)
    altura = (y1 - y0) * escala

    def tx(x, y):  # Revit: y para cima; SVG: y para baixo
        return (x - x0) * escala, (y1 - y) * escala

    tipos = sorted(set(s["tipo"] for s in solidos))
    cor_tipo = dict((t, CORES_TIPO[i % len(CORES_TIPO)]) for i, t in enumerate(tipos))
    maior = max(solidos, key=lambda s: max(abs(_area(p)) for p in s["poligonos"]))

    partes = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
        % (LARGURA, altura + 60, LARGURA, altura + 60),
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for s in solidos:
        if s is maior:
            continue  # terreno geral: só fundo
        d = " ".join(_caminho(p, tx) for p in s["poligonos"])
        partes.append(
            '<path d="%s" fill="%s" fill-opacity="0.6" fill-rule="evenodd" stroke="#555" '
            'stroke-width="0.6"><title>#%s %s</title></path>'
            % (d, cor_tipo[s["tipo"]], s["id"], s["tipo"])
        )
    for r in poligonos:
        partes.append(
            '<path d="%s" fill="none" stroke="%s" stroke-width="0.8"/>'
            % (_caminho(r["poligono"], tx), CORES_STATUS.get(r["status"], "#000"))
        )
    legenda = [(t, cor_tipo[t]) for t in tipos] + list(CORES_STATUS.items())
    for i, (nome, cor) in enumerate(legenda):
        x = 10 + i * 190
        partes.append(
            '<rect x="%d" y="%.0f" width="14" height="14" fill="%s"/>'
            % (x, altura + 20, cor)
        )
        partes.append(
            '<text x="%d" y="%.0f" font-size="13" font-family="sans-serif">%s</text>'
            % (x + 20, altura + 32, nome)
        )
    partes.append("</svg>")
    return "\n".join(partes)


def _area(p):
    return (
        sum(
            p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1]
            for i in range(len(p))
        )
        / 2.0
    )


def main():
    entrada, saida = sys.argv[1], sys.argv[2]
    with open(entrada, encoding="utf-8") as fh:
        dados = json.load(fh)
    with open(saida, "w", encoding="utf-8") as fh:
        fh.write(desenhar(dados))
    print(saida)


if __name__ == "__main__":
    main()
