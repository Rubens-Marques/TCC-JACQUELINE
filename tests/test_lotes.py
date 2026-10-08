# -*- coding: utf-8 -*-
"""Regras do script de lotes (partes sem Revit + criação contra um Revit simulado)."""

import json
import os
import sys
import unittest
from types import SimpleNamespace as NS

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "automacao", "scripts")
)
import tcc_lotes  # noqa: E402

RET = lambda x0, y0, x1, y1: [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]  # noqa: E731


def topo(tid, poligono, host_id=None, furos=(), outros=(), tipo="T"):
    """Sólido com os polígonos do esboço: contornos e furos juntos (regra par-ímpar)."""
    return {
        "id": tid,
        "host_id": host_id,
        "poligonos": [poligono] + list(outros) + list(furos),
        "tipo": tipo,
    }


class ConfigTest(unittest.TestCase):
    def test_json_vazio_usa_padrao_e_piloto_de_10(self):
        cfg = tcc_lotes.ler_config("")
        self.assertEqual(cfg["limite"], 10)
        self.assertIn("BASE REVIT", cfg["dwg"])

    def test_json_sobrescreve_so_o_informado(self):
        cfg = tcc_lotes.ler_config('{"limite": 0, "camadas": ["LOTES"]}')
        self.assertEqual((cfg["limite"], cfg["camadas"]), (0, ["LOTES"]))
        self.assertEqual(cfg["tolerancia_m"], tcc_lotes.CONFIG_PADRAO["tolerancia_m"])

    def test_json_invalido_explica_o_erro(self):
        with self.assertRaises(ValueError) as erro:
            tcc_lotes.ler_config("{limite: 0}")
        self.assertIn("JSON", str(erro.exception))


class CamadasTest(unittest.TestCase):
    DISPONIVEIS = ["0", "EIXO_VIAS", "LOTES", "Quadras", "TEXTO_LOTE_NUM", "CURVAS"]

    def test_automatico_pega_lote_e_quadra_e_ignora_texto(self):
        self.assertEqual(
            tcc_lotes.escolher_camadas(self.DISPONIVEIS, []),
            ["LOTES", "Quadras"],
        )

    def test_automatico_entende_camadas_de_xref_do_dwg_base_revit(self):
        # Nomes reais do "Arquivo Completo- BASE REVIT.dwg" (xref ligado: <xref>$0$<camada>).
        disponiveis = [
            "(sem camada)",
            "Bai$0$Bai",
            "Corte",
            "Lot$0$Corte",
            "Lot$0$Lot",
            "MEIO FIO",
            "Qdr$0$Qdr",
            "TRABALHO CURVA$0$Cnv$0$Cnv",
            "TRABALHO CURVA$0$Hid$0$Hid",
        ]
        self.assertEqual(
            tcc_lotes.escolher_camadas(disponiveis, []), ["Lot$0$Lot", "Qdr$0$Qdr"]
        )

    def test_lista_explicita_ignora_maiusculas(self):
        self.assertEqual(
            tcc_lotes.escolher_camadas(self.DISPONIVEIS, ["lotes"]), ["LOTES"]
        )


class PlanejarTest(unittest.TestCase):
    def setUp(self):
        self.cfg = tcc_lotes.ler_config('{"limite": 0}')
        terreno = topo(1, RET(-100, -100, 300, 300))
        quadra = topo(2, RET(0, 0, 40, 30))  # quadra = toposolid próprio
        quadra_sub = topo(
            3, RET(100, 0, 140, 30), host_id=1
        )  # quadra = subdivisão do terreno
        calcada = topo(4, RET(-3, -3, 43, 33), host_id=2, furos=[RET(0, 0, 40, 30)])
        self.topos = [terreno, quadra, quadra_sub, calcada]

    def test_lote_vira_subdivisao_da_quadra_que_o_contem(self):
        lotes, _ = tcc_lotes.planejar_lotes([RET(0, 0, 20, 30)], self.topos, self.cfg)
        self.assertEqual((lotes[0]["host_id"], lotes[0]["zona_id"]), (2, 2))

    def test_quadra_que_e_subdivisao_hospeda_no_pai(self):
        lotes, _ = tcc_lotes.planejar_lotes(
            [RET(100, 0, 120, 30)], self.topos, self.cfg
        )
        self.assertEqual((lotes[0]["host_id"], lotes[0]["zona_id"]), (1, 3))

    def test_furo_da_calcada_nao_conta_como_calcada(self):
        lotes, _ = tcc_lotes.planejar_lotes([RET(20, 0, 40, 30)], self.topos, self.cfg)
        self.assertEqual(lotes[0]["zona_id"], 2)

    def test_fora_das_quadras_e_tamanhos_absurdos_sao_rejeitados(self):
        poligonos = [
            RET(200, 200, 220, 230),
            RET(0, 0, 1, 1),
            RET(-100, -100, 300, 300),
        ]
        lotes, rejeitados = tcc_lotes.planejar_lotes(poligonos, self.topos, self.cfg)
        self.assertEqual(lotes, [])
        self.assertEqual(
            rejeitados, {"fora_das_quadras": 1, "area_pequena": 1, "area_grande": 1}
        )

    def test_subdivisao_com_varias_quadras_no_mesmo_esboco(self):
        varias = topo(5, RET(200, 0, 240, 30), host_id=1, outros=[RET(260, 0, 300, 30)])
        lotes, rejeitados = tcc_lotes.planejar_lotes(
            [RET(200, 0, 220, 30), RET(260, 0, 280, 30)], self.topos + [varias], self.cfg)
        self.assertEqual([l["zona_id"] for l in lotes], [5, 5])
        self.assertEqual(rejeitados, {})

    def test_lote_no_furo_da_calcada_vira_subdivisao_do_terreno(self):
        # Modelo real: a quadra é um anel de CALÇADA (subdivisão do terreno); os lotes vão no furo.
        terreno = topo(1, RET(-100, -100, 1000, 1000), tipo=".RUA")
        calcada = topo(6, RET(497, -3, 543, 33), host_id=1, furos=[RET(500, 0, 540, 30)], tipo="CALÇADA 2")
        lotes, rejeitados = tcc_lotes.planejar_lotes([RET(500, 0, 520, 30)], [terreno, calcada], self.cfg)
        self.assertEqual(rejeitados, {})
        self.assertEqual((lotes[0]["zona_id"], lotes[0]["host_id"]), (6, 1))

    def test_lote_ja_modelado_nao_e_recriado(self):
        terreno = topo(1, RET(-100, -100, 1000, 1000), tipo=".RUA")
        calcada = topo(6, RET(497, -3, 543, 33), host_id=1, furos=[RET(500, 0, 540, 30)], tipo="CALÇADA 2")
        manual = topo(7, RET(500, 0, 520, 30), host_id=1, tipo=".LOTE")
        registro = []
        lotes, rejeitados = tcc_lotes.planejar_lotes(
            [RET(500, 0, 520, 30), RET(520, 0, 540, 30)], [terreno, calcada, manual], self.cfg, registro)
        self.assertEqual(rejeitados, {"ja_modelado": 1})
        self.assertEqual([l["zona_id"] for l in lotes], [6])
        self.assertEqual(registro[0]["zona_id"], 7)

    def test_registro_guarda_o_destino_de_cada_poligono(self):
        registro = []
        tcc_lotes.planejar_lotes([RET(0, 0, 20, 30), RET(200, 200, 220, 230)], self.topos, self.cfg, registro)
        self.assertEqual([(r["status"], r["zona_id"]) for r in registro], [("lote", 2), ("fora_das_quadras", None)])

    def test_maior_toposolid_e_o_terreno_e_nao_conta_como_quadra(self):
        # Sem a quadra 2, o lote só cairia no terreno geral → rejeitado.
        topos = [t for t in self.topos if t["id"] not in (2, 4)]
        _, rejeitados = tcc_lotes.planejar_lotes([RET(0, 0, 20, 30)], topos, self.cfg)
        self.assertEqual(rejeitados, {"fora_das_quadras": 1})


class EsbocoTest(unittest.TestCase):
    @staticmethod
    def segmentos(*poligonos):
        return [(p[i], p[(i + 1) % len(p)]) for p in poligonos for i in range(len(p))]

    def test_anel_da_calcada_guarda_contorno_e_furo(self):
        poligonos = tcc_lotes.poligonos_do_esboco(self.segmentos(RET(-3, -3, 43, 33), RET(0, 0, 40, 30)))
        self.assertEqual(sorted(round(tcc_lotes.area(p)) for p in poligonos), [1200, 46 * 36])

    def test_esboco_com_varias_quadras_guarda_todas(self):
        poligonos = tcc_lotes.poligonos_do_esboco(
            self.segmentos(RET(0, 0, 40, 30), RET(60, 0, 100, 30), RET(120, 0, 160, 30)))
        self.assertEqual(len(poligonos), 3)


# --- Revit simulado para a etapa de criação ---------------------------------------------


class Param(object):
    def __init__(self, valor=None):
        self.valor = valor

    def AsString(self):
        return self.valor

    def Set(self, valor):
        self.valor = valor


class Topo(object):
    def __init__(self, tid, falhar=False):
        self.Id = NS(Value=tid)
        self.falhar = falhar
        self.criados = []
        self.comentario = Param()

    def get_Parameter(self, _bip):
        return self.comentario

    def CreateSubDivision(self, _doc, *args):
        if self.falhar:
            raise Exception("loops intersect")
        novo = Topo(1000 + len(self.criados))
        self.criados.append((args, novo))
        return novo


class Transacao(object):
    """Transação falsa: `recusar` simula o Revit desfazendo na confirmação."""

    log = []
    recusar = {}  # nº da transação (1, 2, ...) → (erros, avisos)

    def __init__(self, nome):
        self.n = len([x for x in Transacao.log if x == "start"]) + 1

    def iniciar(self):
        Transacao.log.append("start")

    def confirmar(self):
        erros, avisos = Transacao.recusar.get(self.n, ([], []))
        Transacao.log.append("rollback-revit" if erros else "commit")
        return not erros, erros, avisos

    def desfazer(self):
        Transacao.log.append("rollback")


def db_falso():
    curve_loop = type(
        "CurveLoop",
        (),
        {
            "__init__": lambda s: setattr(s, "c", []),
            "Append": lambda s, c: s.c.append(c),
        },
    )
    return NS(
        CurveLoop=curve_loop,
        Line=NS(CreateBound=lambda a, b: (a, b)),
        XYZ=lambda x, y, z: (x, y, z),
        BuiltInParameter=NS(ALL_MODEL_INSTANCE_COMMENTS="comentarios"),
        ElementId=NS(InvalidElementId=NS(Value=-1)),
    )


class CriarTest(unittest.TestCase):
    def setUp(self):
        Transacao.log, Transacao.recusar = [], {}
        self.db = db_falso()
        self.lote = {"poligono": RET(0, 0, 20, 30), "host_id": 2, "zona_id": 2, "area": 600.0}

    def criar(self, lotes, hosts, tipo=None):
        return tcc_lotes.criar_lotes(None, self.db, lotes, hosts, tipo, lista=list, nova_transacao=Transacao)

    def test_cria_subdivisao_marcada_em_pes(self):
        host = Topo(2)
        resultado = self.criar([self.lote], {2: host})
        self.assertEqual((resultado["criados"], resultado["ids"]), (1, [1000]))
        (args, novo) = host.criados[0]
        self.assertEqual(novo.comentario.valor, tcc_lotes.MARCA)
        (loop,) = args[0]
        self.assertAlmostEqual(loop.c[0][1][0], 20 / 0.3048)  # 20 m → pés
        self.assertEqual(len(loop.c), 4)

    def test_excecao_na_criacao_desfaz_so_aquele_lote(self):
        hosts = {2: Topo(2, falhar=True), 3: Topo(3)}
        resultado = self.criar([self.lote, dict(self.lote, host_id=3)], hosts)
        self.assertEqual(resultado["criados"], 1)
        self.assertIn("loops intersect", resultado["erros"][0])
        self.assertEqual(Transacao.log, ["start", "rollback", "start", "commit"])

    def test_revit_desfazendo_na_confirmacao_nao_conta_como_criado(self):
        # O bug do piloto: o relatório dizia "Criados: 10" e o Revit desfez tudo depois.
        Transacao.recusar = {1: (["Subdivisões não podem se sobrepor."], [])}
        resultado = self.criar([self.lote, dict(self.lote, zona_id=3)], {2: Topo(2)})
        self.assertEqual(resultado["criados"], 1)
        self.assertEqual(len(resultado["erros"]), 1)
        self.assertIn("Revit desfez: Subdivisões não podem se sobrepor.", resultado["erros"][0])

    def test_avisos_do_revit_sao_contados_sem_impedir_o_lote(self):
        Transacao.recusar = {}
        original = Transacao.confirmar
        Transacao.confirmar = lambda self: (True, [], ["Linha muito curta."])
        try:
            resultado = self.criar([self.lote, self.lote], {2: Topo(2)})
        finally:
            Transacao.confirmar = original
        self.assertEqual(resultado["criados"], 2)
        self.assertEqual(resultado["avisos"], {"Linha muito curta.": 2})

    def test_tipo_informado_usa_sobrecarga_com_tipo(self):
        host = Topo(2)
        self.criar([self.lote], {2: host}, tipo="tipo-lote")
        self.assertEqual(host.criados[0][0][0], "tipo-lote")


class LimiteTest(unittest.TestCase):
    def test_piloto_pega_lotes_da_mesma_quadra_primeiro(self):
        lotes = [
            {"zona_id": 9, "poligono": RET(50, 0, 60, 10)},
            {"zona_id": 2, "poligono": RET(10, 0, 20, 10)},
            {"zona_id": 2, "poligono": RET(0, 0, 10, 10)},
        ]
        escolhidos = tcc_lotes.aplicar_limite(lotes, 2)
        self.assertEqual([l["zona_id"] for l in escolhidos], [2, 2])

    def test_limite_zero_e_todos(self):
        self.assertEqual(
            len(
                tcc_lotes.aplicar_limite(
                    [{"zona_id": 1, "poligono": RET(0, 0, 1, 1)}] * 3, 0
                )
            ),
            3,
        )


if __name__ == "__main__":
    unittest.main()


# --- Simulação completa contra um documento falso ------------------------------------


class Pt(object):
    def __init__(self, x_m, y_m):
        self.X, self.Y, self.Z = x_m / 0.3048, y_m / 0.3048, 0.0


def fake_db_documento(pasta, deslocamentos_dwg=((0, 0),)):
    """Cada deslocamento (m) é uma cópia do DWG; o Revit chama a 2ª de "... (2)"."""
    class Curve(object):
        def __init__(self, pts):
            self.pts = pts

        def Tessellate(self):
            return self.pts

        def GetType(self):
            return NS(Name="Line")

    class PolyLine(object):
        def __init__(self, pts, estilo):
            self.pts, self.GraphicsStyleId = pts, estilo

        def GetCoordinates(self):
            return self.pts

    class GeometryInstance(object):
        def __init__(self, objs):
            self.objs = objs

        def GetInstanceGeometry(self):
            return self.objs

    classes = dict(
        (n, type(n, (), {})) for n in ("ImportInstance", "Toposolid", "ToposolidType")
    )
    db = NS(
        Curve=Curve,
        PolyLine=PolyLine,
        GeometryInstance=GeometryInstance,
        Options=lambda: None,
        BuiltInParameter=NS(ALL_MODEL_INSTANCE_COMMENTS="c", ALL_MODEL_TYPE_NAME="t"),
        Element=NS(Name=NS(__get__=lambda e: e.Name)),
        **classes,
    )

    def contorno_pts(x0, y0, x1, y1):
        return [Pt(x0, y0), Pt(x1, y0), Pt(x1, y1), Pt(x0, y1), Pt(x0, y0)]

    elementos = {
        "est-lotes": NS(GraphicsStyleCategory=NS(Name="LOTES")),
        "est-eixo": NS(GraphicsStyleCategory=NS(Name="EIXO")),
        "tipo-q": NS(Name="Quadra"),
    }

    def topo(tid, rect, host=-1):
        elementos["sk%d" % tid] = NS(Profile=[[Curve(contorno_pts(*rect))]])
        return NS(
            Id=NS(Value=tid),
            HostTopoId=NS(Value=host),
            SketchId="sk%d" % tid,
            GetTypeId=lambda: "tipo-q",
            get_Parameter=lambda _b: Param(),
        )

    def dwg(indice, dx, dy):
        geometria = [
            GeometryInstance(
                [
                    PolyLine(contorno_pts(dx, dy, dx + 40, dy + 30), "est-lotes"),
                    PolyLine([Pt(dx + 20, dy), Pt(dx + 20, dy + 30)], "est-lotes"),
                    PolyLine([Pt(dx - 50, dy + 15), Pt(dx + 90, dy + 15)], "est-eixo"),
                ]
            )
        ]
        sufixo = " (%d)" % (indice + 1) if indice else ""
        return NS(
            Id=NS(Value=77 + indice),
            Category=NS(Name="Arquivo Completo- BASE REVIT.dwg" + sufixo),
            get_Geometry=lambda _o: geometria,
        )

    por_classe = {
        classes["ImportInstance"]: [dwg(i, dx, dy) for i, (dx, dy) in enumerate(deslocamentos_dwg)],
        classes["Toposolid"]: [
            topo(1, (-100, -100, 300, 300)),
            topo(2, (-3, -3, 43, 33)),
        ],
        classes["ToposolidType"]: [NS(Name="Quadra", Id="tipo-q"), NS(Name=".LOTE", Id="tipo-lote")],
    }

    class Coletor(object):
        def __init__(self, _doc):
            pass

        def OfClass(self, cls):
            return por_classe[cls]

    db.FilteredElementCollector = Coletor
    doc = NS(
        Title="TERRENO",
        PathName=os.path.join(pasta, "TERRENO.rvt"),
        GetElement=elementos.get,
    )
    return db, doc


class SimulacaoTest(unittest.TestCase):
    def test_simulacao_relata_camadas_lotes_e_nao_cria_nada(self):
        import tempfile

        with tempfile.TemporaryDirectory() as pasta:
            db, doc = fake_db_documento(pasta)
            relatorio = tcc_lotes.executar(doc, db, False, "")
            with open(os.path.join(pasta, "lotes_TERRENO.json"), encoding="utf-8") as fh:
                salvo = json.load(fh)
        self.assertEqual(len(salvo["lotes"]), 2)
        self.assertEqual([s["id"] for s in salvo["solidos"]], [1, 2])
        self.assertEqual(sorted(p["status"] for p in salvo["poligonos_dwg"]), ["lote", "lote"])
        self.assertIn("Zonas por tipo:", relatorio)
        self.assertIn("SIMULAÇÃO", relatorio)
        self.assertIn("[x] LOTES", relatorio)
        self.assertIn("[ ] EIXO", relatorio)
        self.assertIn("Lotes aceitos: 2 em 1 quadras", relatorio)
        self.assertIn("seriam criados 2 lotes", relatorio)
        self.assertIn("Tipo do lote: .LOTE · disponíveis: .LOTE, Quadra", relatorio)

    def test_tipo_inexistente_lista_os_disponiveis(self):
        import tempfile

        with tempfile.TemporaryDirectory() as pasta:
            db, doc = fake_db_documento(pasta)
            with self.assertRaises(ValueError) as erro:
                tcc_lotes.executar(doc, db, False, '{"tipo_lote": "Gramado"}')
        self.assertIn(".LOTE, Quadra", str(erro.exception))

    def test_escolhe_a_copia_do_dwg_que_cai_sobre_as_quadras(self):
        import tempfile

        with tempfile.TemporaryDirectory() as pasta:
            db, doc = fake_db_documento(pasta, deslocamentos_dwg=[(5000, 5000), (0, 0)])
            relatorio = tcc_lotes.executar(doc, db, False, "")
        self.assertIn("DWG usado: Arquivo Completo- BASE REVIT.dwg (2) #78", relatorio)
        self.assertIn("#77: 0 de 5 segmentos sobre os sólidos", relatorio)
        self.assertIn("Lotes aceitos: 2 em 1 quadras", relatorio)

    def test_sem_sobreposicao_mostra_onde_estao_dwg_e_solidos(self):
        import tempfile

        with tempfile.TemporaryDirectory() as pasta:
            db, doc = fake_db_documento(pasta, deslocamentos_dwg=[(5000, 5000)])
            relatorio = tcc_lotes.executar(doc, db, False, "")
        self.assertIn("Nenhuma linha das camadas escolhidas cai sobre os sólidos", relatorio)
        self.assertIn("Sólidos ocupam: x -101 a 301 · y -101 a 301", relatorio)
        self.assertIn("#77: 0 de 5 segmentos sobre os sólidos · linhas em x 5000 a 5040 · y 5000 a 5030", relatorio)
        self.assertNotIn("Lotes aceitos", relatorio)


# --- Lote-modelo, numeração e sobreposição ------------------------------------------


class ModeloTest(unittest.TestCase):
    def setUp(self):
        self.cfg = tcc_lotes.ler_config("")
        self.topos = [
            topo(1, RET(-100, -100, 1000, 1000), tipo=".RUA"),
            topo(10, RET(0, 0, 10, 30), host_id=1, tipo=".LOTE"),  # 300 m²
            topo(11, RET(10, 0, 22, 30), host_id=1, tipo=".LOTE"),  # 360 m²
            topo(12, RET(22, 0, 37, 30), host_id=1, tipo=".LOTE"),  # 450 m²
            topo(13, RET(100, 100, 260, 275), host_id=1, tipo=".LOTE"),  # 28.000 m²: terreno do CTJ
            topo(14, RET(0, 40, 10, 70), host_id=1, tipo=".LOTE"),
            topo(20, RET(-3, -3, 43, 33), host_id=1, furos=[RET(0, 0, 40, 30)], tipo="CALÇADA 2"),
        ]
        self.topos[5]["marca"] = tcc_lotes.MARCA  # criado pelo script: não serve de modelo

    def test_modelo_e_o_lote_manual_de_area_mediana(self):
        self.assertEqual(tcc_lotes.escolher_modelo(self.topos, self.cfg)["id"], 11)

    def test_modelo_informado_no_json_prevalece(self):
        cfg = tcc_lotes.ler_config('{"modelo_id": 12}')
        self.assertEqual(tcc_lotes.escolher_modelo(self.topos, cfg)["id"], 12)

    def test_sem_lote_manual_nao_ha_modelo(self):
        self.assertIsNone(tcc_lotes.escolher_modelo(self.topos[:1], self.cfg))


class ParametrosTest(unittest.TestCase):
    @staticmethod
    def param(nome, storage, valor, bip=None, somente_leitura=False):
        return NS(
            Definition=NS(Name=nome, BuiltInParameter=bip),
            IsReadOnly=somente_leitura,
            StorageType=storage,
            HasValue=True,
            AsDouble=lambda: valor,
            AsInteger=lambda: valor,
            AsString=lambda: valor,
            AsElementId=lambda: valor,
            AsValueString=lambda: str(valor),
        )

    def test_copia_editaveis_e_ignora_marca_comentario_e_somente_leitura(self):
        db = NS(
            StorageType=NS(Double="D", Integer="I", String="S", ElementId="E", NONE="N"),
            BuiltInParameter=NS(ALL_MODEL_INSTANCE_COMMENTS="com", ALL_MODEL_MARK="mark"),
        )
        modelo = NS(Parameters=[
            self.param("Altura da subdivisão", "D", 0.5),
            self.param("Fase de criação", "E", "fase-1"),
            self.param("Comentários", "S", "manual", bip="com"),
            self.param("Marca", "S", "L7", bip="mark"),
            self.param("Área", "D", 300.0, somente_leitura=True),
        ])
        copiaveis = tcc_lotes.parametros_copiaveis(db, modelo)
        self.assertEqual([c["nome"] for c in copiaveis], ["Altura da subdivisão", "Fase de criação"])

        recebidos = {}
        novo = NS(get_Parameter=lambda d: NS(Set=lambda v, d=d: recebidos.__setitem__(d.Name, v), IsReadOnly=False))
        tcc_lotes.aplicar_parametros(novo, copiaveis)
        self.assertEqual(recebidos, {"Altura da subdivisão": 0.5, "Fase de criação": "fase-1"})


class NumeracaoTest(unittest.TestCase):
    def test_quadras_de_cima_para_baixo_e_lotes_da_esquerda_para_a_direita(self):
        lotes = [
            {"zona_id": 5, "poligono": RET(20, 0, 30, 10)},
            {"zona_id": 9, "poligono": RET(0, 100, 10, 110)},  # quadra mais ao norte → Q01
            {"zona_id": 5, "poligono": RET(0, 0, 10, 10)},
        ]
        tcc_lotes.numerar(lotes)
        self.assertEqual([l["marca"] for l in lotes], ["Q02-L02", "Q01-L01", "Q02-L01"])


class SobreposicaoTest(unittest.TestCase):
    def test_reconhece_aviso_de_sobreposicao_em_portugues_e_ingles(self):
        self.assertTrue(tcc_lotes.e_sobreposicao("As subdivisões realçadas se sobrepõem."))
        self.assertTrue(tcc_lotes.e_sobreposicao("Highlighted subdivisions overlap."))
        self.assertFalse(tcc_lotes.e_sobreposicao("Linha muito curta."))
