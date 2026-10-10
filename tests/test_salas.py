# -*- coding: utf-8 -*-
"""Regras do script Salas → Paredes (partes sem Revit)."""

import math
import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "automacao", "scripts")
)
from tcc_geometria import area  # noqa: E402
import tcc_salas  # noqa: E402

RET = lambda x0, y0, x1, y1: [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]  # noqa: E731


def sala(sid, *lacos, **extra):
    s = {"id": sid, "lacos": list(lacos), "sem_parede": False}
    s.update(extra)
    return s


def comprimento(paredes, tipo):
    return sum(math.hypot(p["b"][0] - p["a"][0], p["b"][1] - p["a"][1]) for p in paredes if p["tipo"] == tipo)


class PlanejarParedesTest(unittest.TestCase):
    def test_sala_sozinha_vira_quatro_externas(self):
        paredes = tcc_salas.planejar_paredes([sala(1, RET(0, 0, 4, 3))])
        self.assertEqual(len(paredes), 4)
        self.assertTrue(all(p["tipo"] == "externa" for p in paredes))
        self.assertAlmostEqual(comprimento(paredes, "externa"), 14.0)

    def test_borda_comum_vira_uma_parede_interna_so(self):
        paredes = tcc_salas.planejar_paredes([sala(1, RET(0, 0, 4, 3)), sala(2, RET(4, 0, 8, 3))])
        internas = [p for p in paredes if p["tipo"] == "interna"]
        self.assertEqual(len(internas), 1)
        self.assertAlmostEqual(comprimento(paredes, "interna"), 3.0)
        self.assertEqual(internas[0]["salas"], [1, 2])
        # contorno externo 8x3 = 22 m, com as faixas superior/inferior unidas numa parede só
        self.assertAlmostEqual(comprimento(paredes, "externa"), 22.0)
        self.assertEqual(len(paredes), 5)

    def test_sala_grande_encostada_em_duas_pequenas_quebra_no_t(self):
        # corredor 0..8 embaixo; duas salas em cima, 0..3 e 3..8
        salas = [sala("c", RET(0, 0, 8, 2)), sala("a", RET(0, 2, 3, 6)), sala("b", RET(3, 2, 8, 6))]
        paredes = tcc_salas.planejar_paredes(salas)
        self.assertAlmostEqual(comprimento(paredes, "interna"), 8.0 + 4.0)
        self.assertAlmostEqual(comprimento(paredes, "externa"), 2 * 8 + 2 * 6)

    def test_pisos_com_vao_da_parede_entre_eles_viram_parede_no_meio(self):
        paredes = tcc_salas.planejar_paredes(
            [sala(1, RET(0, 0, 4, 3)), sala(2, RET(4.15, 0, 8, 3))], junta_max_m=0.30)
        internas = [p for p in paredes if p["tipo"] == "interna"]
        self.assertEqual(len(internas), 1)
        self.assertAlmostEqual(internas[0]["a"][0], 4.075, places=3)

    def test_vao_maior_que_a_junta_sao_duas_externas(self):
        paredes = tcc_salas.planejar_paredes(
            [sala(1, RET(0, 0, 4, 3)), sala(2, RET(5, 0, 8, 3))], junta_max_m=0.30)
        self.assertFalse([p for p in paredes if p["tipo"] == "interna"])

    def test_patio_sem_parede_deixa_a_borda_vizinha_como_externa(self):
        salas = [sala(1, RET(0, 0, 4, 3)), sala(2, RET(4, 0, 8, 3), sem_parede=True)]
        paredes = tcc_salas.planejar_paredes(salas)
        self.assertEqual(len(paredes), 4)
        self.assertTrue(all(p["salas"] == [1] for p in paredes))

    def test_fora_aponta_para_o_lado_de_fora(self):
        paredes = tcc_salas.planejar_paredes([sala(1, RET(0, 0, 4, 3))])
        for p in paredes:
            meio = ((p["a"][0] + p["b"][0]) / 2, (p["a"][1] + p["b"][1]) / 2)
            fora = (meio[0] + p["fora"][0], meio[1] + p["fora"][1])
            self.assertFalse(tcc_salas.dentro_da_sala(fora, [RET(0, 0, 4, 3)]))

    def test_deslocar_externa_meia_espessura(self):
        p = {"a": (0, 0), "b": (4, 0), "fora": (0, -1)}
        a, b = tcc_salas.deslocar_externa(p, 0.20)
        self.assertAlmostEqual(a[1], -0.10)
        self.assertAlmostEqual(b[1], -0.10)

    def test_sala_com_furo_ganha_parede_em_volta_do_shaft(self):
        paredes = tcc_salas.planejar_paredes([sala(1, RET(0, 0, 10, 10), RET(4, 4, 6, 6))])
        self.assertAlmostEqual(comprimento(paredes, "externa"), 40 + 8)

    def test_borda_inclinada(self):
        tri = [(0, 0), (4, 0), (0, 4)]
        vizinho = [(4, 0), (4, 4), (0, 4)]
        paredes = tcc_salas.planejar_paredes([sala(1, tri), sala(2, vizinho)])
        internas = [p for p in paredes if p["tipo"] == "interna"]
        self.assertEqual(len(internas), 1)
        self.assertAlmostEqual(comprimento(paredes, "interna"), math.hypot(4, 4), places=4)


class SalasTest(unittest.TestCase):
    def test_ponto_interno_de_sala_em_l(self):
        l = [(0, 0), (10, 0), (10, 2), (2, 2), (2, 10), (0, 10)]
        p = tcc_salas.ponto_interno([l])
        self.assertTrue(tcc_salas.dentro_da_sala(p, [l]))

    def test_ponto_interno_desvia_do_furo(self):
        lacos = [RET(0, 0, 10, 10), RET(3, 3, 7, 7)]
        self.assertTrue(tcc_salas.dentro_da_sala(tcc_salas.ponto_interno(lacos), lacos))

    def test_area_desconta_furo(self):
        self.assertAlmostEqual(tcc_salas.area_salas([RET(0, 0, 10, 10), RET(3, 3, 7, 7)]), 84.0)

    def test_sem_parede_ignora_acento_e_caixa(self):
        padroes = tcc_salas.CONFIG_PADRAO["sem_parede"]
        self.assertTrue(tcc_salas.sem_parede("Pátio Central", padroes))
        self.assertTrue(tcc_salas.sem_parede("PERGOLADO", padroes))
        self.assertFalse(tcc_salas.sem_parede("Sala de aula 01", padroes))

    def test_setor_do_material_com_mapa(self):
        cfg = tcc_salas.ler_config('{"mapa_setores": {"Setor-ESP": "Esportivo"}}')
        self.assertEqual(tcc_salas.nome_setor("Setor-ESP", "Piso 10", cfg), "Esportivo")
        self.assertEqual(tcc_salas.nome_setor("", "Piso 10", cfg), "(sem setor)")
        cfg = tcc_salas.ler_config('{"setor_de": "tipo"}')
        self.assertEqual(tcc_salas.nome_setor("Concreto", "Cultural", cfg), "Cultural")

    def test_resumo_e_csv(self):
        salas = [
            {"id": 1, "nome": "Sala 1", "setor": "Educ", "area": 40.0, "nivel": "Térreo", "elev": 0.0},
            {"id": 2, "nome": "Sala 2", "setor": "Educ", "area": 35.5, "nivel": "Térreo", "elev": 0.0},
            {"id": 3, "nome": "Quadra", "setor": "Esporte", "area": 600.0, "nivel": "Térreo", "elev": 0.0},
        ]
        self.assertEqual(tcc_salas.resumo_setores(salas)[0], ("Esporte", 1, 600.0))
        csv = tcc_salas.tabela_csv(salas)
        self.assertIn("Térreo;Sala 2;Educ;35,50;2", csv)
        self.assertTrue(csv.startswith("pavimento;sala;setor;area_m2"))

    def test_problemas_apontam_piso_minusculo(self):
        salas = [{"id": 1, "nome": "X", "setor": "s", "area": 0.2, "nivel": "T", "elev": 0}]
        self.assertTrue(tcc_salas.problemas_das_salas(salas))

    def test_json_invalido_explica(self):
        with self.assertRaises(ValueError):
            tcc_salas.ler_config("{'x': 1}")


if __name__ == "__main__":
    unittest.main()


# --- Revit simulado: só o necessário para a SIMULAÇÃO rodar de ponta a ponta ---------

from types import SimpleNamespace as NS  # noqa: E402

FT = 0.3048


class _Id(object):
    def __init__(self, v):
        self.Value = v


class _Param(object):
    def __init__(self, valor=""):
        self.valor, self.IsReadOnly = valor, False

    def AsString(self):
        return self.valor

    def Set(self, v):
        self.valor = v


class _Linha(object):
    def __init__(self, a, b):
        self.pts = [NS(X=a[0] / FT, Y=a[1] / FT), NS(X=b[0] / FT, Y=b[1] / FT)]

    def Tessellate(self):
        return self.pts


class _FakeDB(object):
    class BuiltInParameter:
        ALL_MODEL_INSTANCE_COMMENTS = "comments"
        ALL_MODEL_TYPE_NAME = "type_name"

    class BuiltInCategory:
        OST_Rooms = "rooms"

    class WallKind:
        Basic = "basic"

    Line = _Linha
    Element = NS(Name=NS(__get__=lambda e: e.Name))

    class Floor(object):
        pass

    class Wall(object):
        pass

    class WallType(object):
        pass

    class FloorType(object):
        pass

    class Level(object):
        pass

    def __init__(self, doc):
        self.doc = doc
        db = self

        class Coletor(object):
            def __init__(self, d):
                self.itens = []

            def OfClass(self, c):
                self.itens = [e for e in db.doc.elementos.values() if isinstance(e, c)]
                return self

            def OfCategory(self, c):
                self.itens = []
                return self

            def WhereElementIsNotElementType(self):
                return self

            def __iter__(self):
                return iter(self.itens)

        self.FilteredElementCollector = Coletor


class _Generico(object):
    pass


def _elemento(classe, eid, **campos):
    e = classe()
    e.Id = _Id(eid)
    e.__dict__.update(campos)
    params = campos.pop("params", {})
    e.get_Parameter = lambda p: params.get(p)
    return e


class SimulacaoTest(unittest.TestCase):
    def test_simulacao_relata_setores_paredes_e_nao_altera_nada(self):
        import tempfile

        pasta = tempfile.mkdtemp()
        doc = NS(elementos={}, PathName=os.path.join(pasta, "CTJ.rvt"))
        DB = _FakeDB(doc)
        nivel = _elemento(DB.Level, 10, Name="Térreo", Elevation=0.0)
        mat = _elemento(_Generico, 20, Name="Setor Educacional")
        tipo_piso = _elemento(DB.FloorType, 30, Name="Piso sala",
                              GetCompoundStructure=lambda: None)
        parede = _elemento(DB.WallType, 40, Name="Parede 15", Kind="basic", Width=0.15 / FT)
        doc.elementos.update({10: nivel, 20: mat, 30: tipo_piso, 40: parede})

        def piso(eid, nome, ret):
            pts = ret + ret[:1]
            sketch = NS(Profile=[[_Linha(a, b) for a, b in zip(pts, pts[1:])]])
            doc.elementos[eid + 1000] = sketch
            return _elemento(DB.Floor, eid, LevelId=10, SketchId=eid + 1000,
                             GetTypeId=lambda: 30, GetMaterialIds=lambda pintado: [20] if pintado else [],
                             params={"comments": _Param(nome)})

        doc.elementos[1] = piso(1, "Sala 1", RET(0, 0, 4, 3))
        doc.elementos[2] = piso(2, "Sala 2", RET(4, 0, 8, 3))
        doc.GetElement = lambda i: doc.elementos.get(i)

        relatorio = tcc_salas.executar(doc, DB, False, "")
        self.assertIn("SIMULAÇÃO", relatorio)
        self.assertIn("Setor Educacional", relatorio)
        self.assertIn("1 internas (3 m) + 4 externas (22 m)", relatorio)
        self.assertIn("Parede interna: Parede 15 (15 cm)", relatorio)
        self.assertTrue(os.path.exists(os.path.join(pasta, "salas_CTJ.csv")))
