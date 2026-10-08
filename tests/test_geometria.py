# -*- coding: utf-8 -*-
"""Polígonos de lote a partir das linhas soltas do DWG."""

import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "automacao", "scripts")
)
from tcc_geometria import (  # noqa: E402
    area,
    centroide,
    poligonos_de_segmentos,
    ponto_no_poligono,
    simplificar,
)


def contorno(pontos):
    """Polilinha fechada → segmentos."""
    return [(pontos[i], pontos[(i + 1) % len(pontos)]) for i in range(len(pontos))]


def areas(poligonos):
    return sorted(round(area(p), 3) for p in poligonos)


class AreaTest(unittest.TestCase):
    def test_area_positiva_no_sentido_anti_horario(self):
        self.assertEqual(area([(0, 0), (10, 0), (10, 5), (0, 5)]), 50)

    def test_area_negativa_no_sentido_horario(self):
        self.assertEqual(area([(0, 0), (0, 5), (10, 5), (10, 0)]), -50)

    def test_centroide_do_retangulo(self):
        self.assertEqual(centroide([(0, 0), (10, 0), (10, 4), (0, 4)]), (5, 2))

    def test_ponto_no_poligono(self):
        quadrado = [(0, 0), (10, 0), (10, 10), (0, 10)]
        self.assertTrue(ponto_no_poligono((5, 5), quadrado))
        self.assertFalse(ponto_no_poligono((15, 5), quadrado))


class SimplificarTest(unittest.TestCase):
    def test_remove_vertices_colineares(self):
        poly = [(0, 0), (5, 0), (10, 0), (10, 10), (0, 10), (0, 5)]
        self.assertEqual(simplificar(poly), [(0, 0), (10, 0), (10, 10), (0, 10)])


class PoligonosDeSegmentosTest(unittest.TestCase):
    def test_quadra_com_linha_divisoria_em_t_vira_dois_lotes(self):
        # Contorno da quadra em uma polilinha; divisa entre lotes encosta nele (junção em T).
        segmentos = contorno([(0, 0), (20, 0), (20, 30), (0, 30)])
        segmentos.append(((10, 0), (10, 30)))
        self.assertEqual(areas(poligonos_de_segmentos(segmentos)), [300, 300])

    def test_grade_de_lotes_com_linhas_que_se_cruzam(self):
        segmentos = contorno([(0, 0), (24, 0), (24, 30), (0, 30)])
        segmentos += [
            ((12, -1), (12, 31)),
            ((-1, 15), (25, 15)),
        ]  # passam um pouco do contorno
        self.assertEqual(areas(poligonos_de_segmentos(segmentos)), [180, 180, 180, 180])

    def test_contornos_duplicados_de_lotes_vizinhos_nao_duplicam_lote(self):
        segmentos = contorno([(0, 0), (10, 0), (10, 25), (0, 25)])
        segmentos += contorno([(10, 0), (20, 0), (20, 25), (10, 25)])
        self.assertEqual(areas(poligonos_de_segmentos(segmentos)), [250, 250])

    def test_tolerancia_fecha_folga_pequena_do_desenho(self):
        segmentos = [
            ((0, 0), (10, 0)),
            ((10.004, 0.003), (10, 10)),
            ((10, 10), (0, 10)),
            ((0, 10), (0, 0.002)),
        ]
        (poligono,) = poligonos_de_segmentos(segmentos, tolerancia=0.01)
        self.assertAlmostEqual(area(poligono), 100, places=1)

    def test_linha_solta_nao_gera_poligono(self):
        segmentos = contorno([(0, 0), (10, 0), (10, 10), (0, 10)])
        segmentos.append(((5, 5), (7, 7)))  # traço interno sem fechar nada
        segmentos.append(((30, 30), (40, 30)))  # linha isolada
        self.assertEqual(areas(poligonos_de_segmentos(segmentos)), [100])

    def test_quadras_separadas_nao_geram_poligono_da_rua(self):
        segmentos = contorno([(0, 0), (10, 0), (10, 10), (0, 10)])
        segmentos += contorno([(20, 0), (30, 0), (30, 10), (20, 10)])
        self.assertEqual(areas(poligonos_de_segmentos(segmentos)), [100, 100])

    def test_poligono_sai_simplificado_e_anti_horario(self):
        segmentos = contorno([(0, 0), (20, 0), (20, 30), (0, 30)])
        segmentos.append(((10, 0), (10, 30)))
        for poligono in poligonos_de_segmentos(segmentos):
            self.assertEqual(len(poligono), 4)
            self.assertGreater(area(poligono), 0)


if __name__ == "__main__":
    unittest.main()
