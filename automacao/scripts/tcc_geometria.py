# -*- coding: utf-8 -*-
"""Geometria 2D pura (sem Revit): fecha as linhas soltas do DWG em polígonos de lote.

DWG de prefeitura raramente traz cada lote como polilinha fechada: o contorno da quadra
é uma linha só e as divisas entre lotes encostam nele (junção em T), às vezes passando um
pouco ou parando um pouco antes. Por isso tratamos o desenho como um grafo planar:
quebramos as linhas nos cruzamentos, soldamos pontas próximas, descartamos traços soltos
e percorremos as faces fechadas — cada face mínima é um lote.

Compatível com Python 2.7 (IronPython/pyRevit) e 3 (Dynamo CPython3).
"""

import math
from collections import defaultdict


def area(poligono):
    """Área com sinal (fórmula do laço): positiva = anti-horário."""
    soma = 0.0
    n = len(poligono)
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        soma += x1 * y2 - x2 * y1
    return soma / 2.0


def centroide(poligono):
    a = area(poligono)
    if abs(a) < 1e-12:
        xs = [p[0] for p in poligono]
        ys = [p[1] for p in poligono]
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    cx = cy = 0.0
    n = len(poligono)
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        f = x1 * y2 - x2 * y1
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    return (cx / (6.0 * a), cy / (6.0 * a))


def ponto_no_poligono(ponto, poligono):
    x, y = ponto
    dentro = False
    n = len(poligono)
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_corte = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_corte:
                dentro = not dentro
    return dentro


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def simplificar(poligono, tolerancia=1e-6):
    """Remove pontos repetidos e vértices colineares (as quebras em T deixam vários)."""
    pts = list(poligono)
    mudou = True
    while mudou and len(pts) > 3:
        mudou = False
        for i in range(len(pts)):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
            base = _dist(a, c)
            if _dist(a, b) <= tolerancia or base <= tolerancia:
                colinear = True
            else:
                cruz = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
                colinear = abs(cruz) / base <= tolerancia
            if colinear:
                del pts[i]
                mudou = True
                break
    return pts


class _Soldador(object):
    """Une pontos a menos de `tolerancia` num único nó (hash espacial)."""

    def __init__(self, tolerancia):
        self.tol = tolerancia
        self.celulas = defaultdict(list)
        self.pontos = []

    def no(self, p):
        cx, cy = int(math.floor(p[0] / self.tol)), int(math.floor(p[1] / self.tol))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for idx in self.celulas[(cx + dx, cy + dy)]:
                    if _dist(self.pontos[idx], p) <= self.tol:
                        return idx
        self.pontos.append((float(p[0]), float(p[1])))
        self.celulas[(cx, cy)].append(len(self.pontos) - 1)
        return len(self.pontos) - 1


def _pares_proximos(segmentos, tolerancia):
    """Pares de segmentos cujas caixas se tocam (grade espacial evita o O(n²) completo)."""
    if not segmentos:
        return set()
    comprimentos = sorted(_dist(a, b) for a, b in segmentos)
    celula = max(comprimentos[len(comprimentos) // 2], tolerancia * 10)
    grade = defaultdict(list)
    for i, (a, b) in enumerate(segmentos):
        x0 = int(math.floor((min(a[0], b[0]) - tolerancia) / celula))
        x1 = int(math.floor((max(a[0], b[0]) + tolerancia) / celula))
        y0 = int(math.floor((min(a[1], b[1]) - tolerancia) / celula))
        y1 = int(math.floor((max(a[1], b[1]) + tolerancia) / celula))
        for gx in range(x0, x1 + 1):
            for gy in range(y0, y1 + 1):
                grade[(gx, gy)].append(i)
    pares = set()
    for indices in grade.values():
        for m in range(len(indices)):
            for n in range(m + 1, len(indices)):
                pares.add((indices[m], indices[n]))
    return pares


def _parametro_projecao(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    comp2 = dx * dx + dy * dy
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / comp2
    t = min(1.0, max(0.0, t))
    return t, _dist(p, (a[0] + t * dx, a[1] + t * dy))


def _cortes(segmentos, tolerancia):
    """Para cada segmento, parâmetros t ∈ [0, 1] onde ele precisa ser quebrado."""
    cortes = [set([0.0, 1.0]) for _ in segmentos]
    for i, j in _pares_proximos(segmentos, tolerancia):
        (p, p2), (q, q2) = segmentos[i], segmentos[j]
        # Ponta de um encostando no outro (junção em T, inclusive com folga ≤ tolerância).
        for ponta, alvo, k in (
            (p, segmentos[j], j),
            (p2, segmentos[j], j),
            (q, segmentos[i], i),
            (q2, segmentos[i], i),
        ):
            t, d = _parametro_projecao(ponta, alvo[0], alvo[1])
            if d <= tolerancia:
                cortes[k].add(t)
        # Cruzamento próprio.
        r = (p2[0] - p[0], p2[1] - p[1])
        s = (q2[0] - q[0], q2[1] - q[1])
        denom = r[0] * s[1] - r[1] * s[0]
        if abs(denom) < 1e-12:
            continue
        qp = (q[0] - p[0], q[1] - p[1])
        t = (qp[0] * s[1] - qp[1] * s[0]) / denom
        u = (qp[0] * r[1] - qp[1] * r[0]) / denom
        if 0.0 < t < 1.0 and 0.0 < u < 1.0:
            cortes[i].add(t)
            cortes[j].add(u)
    return cortes


def _arestas(segmentos, tolerancia):
    soldador = _Soldador(tolerancia)
    arestas = set()
    for (a, b), ts in zip(segmentos, _cortes(segmentos, tolerancia)):
        nos = []
        for t in sorted(ts):
            idx = soldador.no((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
            if not nos or nos[-1] != idx:
                nos.append(idx)
        for u, v in zip(nos, nos[1:]):
            if u != v:
                arestas.add((min(u, v), max(u, v)))
    return soldador.pontos, arestas


def _podar_pontas(arestas):
    """Remove traços que não fecham nada (nós de grau 1, repetidamente)."""
    vizinhos = defaultdict(set)
    for u, v in arestas:
        vizinhos[u].add(v)
        vizinhos[v].add(u)
    pilha = [n for n, viz in vizinhos.items() if len(viz) == 1]
    while pilha:
        n = pilha.pop()
        for m in list(vizinhos[n]):
            vizinhos[m].discard(n)
            if len(vizinhos[m]) == 1:
                pilha.append(m)
        vizinhos[n] = set()
    return dict((n, viz) for n, viz in vizinhos.items() if viz)


def poligonos_de_segmentos(segmentos, tolerancia=0.01, area_minima=None):
    """Faces fechadas mínimas do desenho, como polígonos anti-horários simplificados.

    `segmentos`: lista de ((x1, y1), (x2, y2)) em metros. Segmentos menores que a
    tolerância são ignorados.
    """
    segmentos = [(a, b) for a, b in segmentos if _dist(a, b) > tolerancia]
    pontos, arestas = _arestas(segmentos, tolerancia)
    vizinhos = _podar_pontas(arestas)

    angulo = lambda u, v: math.atan2(
        pontos[v][1] - pontos[u][1], pontos[v][0] - pontos[u][0]
    )  # noqa: E731
    ordenados = dict(
        (u, sorted(viz, key=lambda v, u=u: angulo(u, v))) for u, viz in vizinhos.items()
    )

    if area_minima is None:
        area_minima = tolerancia * tolerancia * 100
    visitadas = set()
    poligonos = []
    for u, viz in ordenados.items():
        for v in viz:
            if (u, v) in visitadas:
                continue
            face = []
            a, b = u, v
            while (a, b) not in visitadas:
                visitadas.add((a, b))
                face.append(pontos[a])
                ao_redor = ordenados[b]
                # Próxima aresta: a imediatamente horária à volta (b→a) — mantém a face à esquerda.
                a, b = b, ao_redor[ao_redor.index(a) - 1]
            if area(face) > area_minima:
                poligonos.append(simplificar(face, tolerancia))
    return poligonos
