# -*- coding: utf-8 -*-
"""Exercita tcc_inventario contra uma API do Revit simulada (o Revit não roda no Mac)."""

import json
import math
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace as NS

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "automacao", "scripts")
)
import tcc_inventario  # noqa: E402


class XYZ(object):
    def __init__(self, x, y, z):
        self.X, self.Y, self.Z = x, y, z


XYZ.Zero = XYZ(0, 0, 0)


class Translacao(object):
    """Interno → compartilhado = soma de um deslocamento (em pés)."""

    def __init__(self, dx, dy, dz):
        self.d = (dx, dy, dz)

    @property
    def Inverse(self):
        return Translacao(-self.d[0], -self.d[1], -self.d[2])

    def OfPoint(self, p):
        return XYZ(p.X + self.d[0], p.Y + self.d[1], p.Z + self.d[2])


class Id(object):
    """Só .Value, como no Revit 2026 (sem IntegerValue)."""

    def __init__(self, value):
        self.Value = value


class Elemento(object):
    def __init__(self, eid, nome=None, bbox=None, tipo=None, categoria=None, **extra):
        self.Id = Id(eid)
        self.Name = nome
        self._bbox = bbox
        self._tipo = tipo
        self.Category = categoria
        self.__dict__.update(extra)

    def get_BoundingBox(self, _view):
        return self._bbox

    def GetTypeId(self):
        return self._tipo or Id(-1)


class Coletor(object):
    def __init__(self, doc):
        self.doc, self.cls = doc, None

    def OfClass(self, cls):
        self.cls = cls
        return self

    def OfCategory(self, _cat):
        return self

    def WhereElementIsNotElementType(self):
        return self

    def __iter__(self):
        return iter(self.doc.por_classe.get(self.cls, []))


def montar_db():
    classes = [
        "Toposolid",
        "ImportInstance",
        "RevitLinkInstance",
        "Level",
        "View",
        "FilledRegionType",
        "ViewSheet",
    ]
    db = NS(**{c: type(c, (), {}) for c in classes})
    db.Architecture = NS(TopographySurface=type("TopographySurface", (), {}))
    db.XYZ = XYZ
    db.BuiltInCategory = NS(OST_Lines="OST_Lines")
    db.FilteredElementCollector = Coletor
    return db


def montar_doc(db):
    origem_compartilhada = Translacao(1000, 2000, 0)
    location = NS(
        Name="Interno",
        GetProjectPosition=lambda _p: NS(
            EastWest=1000, NorthSouth=2000, Elevation=0, Angle=math.radians(12.5)
        ),
        GetTotalTransform=lambda: origem_compartilhada.Inverse,
    )
    survey = NS(Position=XYZ(0, 0, 0), SharedPosition=XYZ(1000, 2000, 0))
    db.BasePoint = NS(
        GetSurveyPoint=lambda _d: survey, GetProjectBasePoint=lambda _d: survey
    )

    caixa = NS(Min=XYZ(0, 0, 700 / 0.3048), Max=XYZ(100, 100, 735 / 0.3048))
    cat_dwg = NS(
        Name="LEVANTAMENTO.dwg", SubCategories=[NS(Name="CURVAS"), NS(Name="LOTES")]
    )
    tipos = {7: NS(Name="Terreno natural")}
    doc = NS(
        Title="TERRENO - JD IPE-TCC",
        PathName="",
        SiteLocation=NS(
            PlaceName="Goiânia",
            Latitude=math.radians(-16.6),
            Longitude=math.radians(-49.3),
        ),
        ActiveProjectLocation=location,
        GetElement=lambda eid: tipos.get(eid.Value),
        Settings=NS(
            Categories=NS(
                get_Item=lambda _c: NS(SubCategories=[NS(Name="<Linhas finas>")])
            )
        ),
    )
    doc.por_classe = {
        db.Toposolid: [Elemento(10, bbox=caixa, tipo=Id(7))],
        db.ImportInstance: [Elemento(20, categoria=cat_dwg, bbox=caixa, IsLinked=True)],
        db.RevitLinkInstance: [],
        db.Level: [
            Elemento(30, nome="720", Elevation=720 / 0.3048),
            Elemento(31, nome="705", Elevation=705 / 0.3048),
        ],
        db.View: [
            Elemento(
                40, nome="Implantação", IsTemplate=False, ViewType="SitePlan", Scale=500
            )
        ],
        db.FilledRegionType: [Elemento(50, nome="Sólido preto")],
        db.ViewSheet: [],
    }
    return doc


class InventarioTest(unittest.TestCase):
    def setUp(self):
        self.db = montar_db()
        self.doc = montar_doc(self.db)
        self.dados = tcc_inventario.inventariar(
            self.doc, "Autodesk Revit 2026", self.db
        )

    def test_localizacao_em_graus_e_metros(self):
        loc = self.dados["localizacao"]
        self.assertAlmostEqual(loc["latitude_graus"], -16.6)
        self.assertEqual(loc["posicao_projeto"]["leste_oeste_m"], 304.8)
        self.assertAlmostEqual(
            loc["posicao_projeto"]["angulo_norte_verdadeiro_graus"], 12.5
        )

    def test_topografia_com_cotas_em_metros_e_coordenada_compartilhada(self):
        topo = self.dados["topografia"][0]
        self.assertEqual(topo["tipo"], "Terreno natural")
        self.assertEqual(topo["caixa"]["compartilhado_min"], [304.8, 609.6, 700.0])
        self.assertEqual(topo["caixa"]["interno_max"][2], 735.0)

    def test_lista_camadas_do_dwg(self):
        self.assertEqual(self.dados["cads"][0]["camadas"], ["CURVAS", "LOTES"])

    def test_niveis_ordenados_por_cota(self):
        self.assertEqual([n["nome"] for n in self.dados["niveis"]], ["705", "720"])

    def test_salva_json_utf8_legivel(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = tcc_inventario.salvar(self.dados, os.path.join(pasta, "inv.json"))
            with open(caminho, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["localizacao"]["local"], "Goiânia")

    def test_resumo_menciona_cotas_e_dwg(self):
        texto = tcc_inventario.resumo(self.dados)
        self.assertIn("cotas 700.0 → 735.0", texto)
        self.assertIn("CAD LEVANTAMENTO.dwg (2 camadas)", texto)


if __name__ == "__main__":
    unittest.main()
