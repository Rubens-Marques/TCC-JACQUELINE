# -*- coding: utf-8 -*-
"""Os .dyn versionados precisam estar em dia com os scripts e nascer em modo seguro."""

import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DYNAMO = ROOT / "automacao" / "dynamo"
SCRIPTS = ROOT / "automacao" / "scripts"

GRAFOS = {
    "TCC_Inventario.dyn": ["tcc_inventario.py"],
    "TCC_Lotes.dyn": ["tcc_geometria.py", "tcc_lotes.py"],
    "TCC_Salas.dyn": ["tcc_geometria.py", "tcc_salas.py"],
}


def carregar(nome):
    return json.loads((DYNAMO / nome).read_text(encoding="utf-8"))


def no_python(grafo):
    nos = [n for n in grafo["Nodes"] if n.get("NodeType") == "PythonScriptNode"]
    assert len(nos) == 1, "esperado exatamente um nó Python"
    return nos[0]


class DynTest(unittest.TestCase):
    def test_codigo_embutido_compila_e_esta_em_dia(self):
        for nome, scripts in GRAFOS.items():
            with self.subTest(grafo=nome):
                codigo = no_python(carregar(nome))["Code"]
                compile(codigo, nome, "exec")
                esperado = "\n\n".join(
                    (SCRIPTS / s).read_text(encoding="utf-8") for s in scripts
                )
                self.assertTrue(
                    codigo.startswith(esperado),
                    "rode: python3 automacao/scripts/build_dyn.py",
                )

    def test_execucao_manual_em_cpython3(self):
        for nome in GRAFOS:
            with self.subTest(grafo=nome):
                grafo = carregar(nome)
                self.assertEqual(grafo["View"]["Dynamo"]["RunType"], "Manual")
                self.assertEqual(no_python(grafo)["Engine"], "CPython3")

    def test_inventario_nao_altera_o_modelo(self):
        codigo = no_python(carregar("TCC_Inventario.dyn"))["Code"]
        for proibido in ("Transaction(", "EnsureInTransaction", ".Delete(", ".Create("):
            self.assertNotIn(proibido, codigo)

    def test_lotes_nasce_em_simulacao_com_piloto(self):
        grafo = carregar("TCC_Lotes.dyn")
        entradas = {
            n["NodeType"]: n
            for n in grafo["Nodes"]
            if n["NodeType"] in ("BooleanInputNode", "StringInputNode")
        }
        self.assertIs(entradas["BooleanInputNode"]["InputValue"], False)
        self.assertEqual(
            json.loads(entradas["StringInputNode"]["InputValue"])["limite"], 10
        )

    def test_salas_nasce_em_simulacao(self):
        grafo = carregar("TCC_Salas.dyn")
        booleano = [n for n in grafo["Nodes"] if n["NodeType"] == "BooleanInputNode"]
        self.assertIs(booleano[0]["InputValue"], False)

    def test_entradas_ligadas_na_ordem_do_script(self):
        grafo = carregar("TCC_Lotes.dyn")
        py = no_python(grafo)
        tipo_por_id = {n["Id"]: n["NodeType"] for n in grafo["Nodes"]}
        ligacoes = {
            c["EndIndex"]: tipo_por_id[c["Start"]]
            for c in grafo["Connectors"]
            if c["End"] == py["Id"]
        }
        self.assertEqual(ligacoes, {0: "BooleanInputNode", 1: "StringInputNode"})


if __name__ == "__main__":
    unittest.main()
