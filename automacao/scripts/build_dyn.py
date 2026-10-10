"""Gera os grafos Dynamo autocontidos (código Python embutido) a partir de automacao/scripts.

Mesmo formato dos grafos do ctj-tcc-revit (Dynamo 3.4, motor CPython3, execução manual).
Rodar sempre que um script mudar:  python3 automacao/scripts/build_dyn.py
"""

import json
import pathlib
import uuid

SCRIPTS = pathlib.Path(__file__).resolve().parent
DYNAMO = SCRIPTS.parent / "dynamo"

# Ponte Dynamo → script: abre o documento, chama a função do script e devolve o relatório
# (ou o traceback completo) para o nó Watch.
CABECALHO_DYNAMO = """

# ---- entrada Dynamo ----
import traceback

import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitServices")
from Autodesk.Revit import DB  # noqa: E402
from RevitServices.Persistence import DocumentManager  # noqa: E402
from RevitServices.Transactions import TransactionManager  # noqa: E402

_doc = DocumentManager.Instance.CurrentDBDocument
"""

ERRO_DYNAMO = """except Exception:
    OUT = "ERRO — copie este texto e mande para análise:\\n" + traceback.format_exc()
"""

ENTRADA_INVENTARIO = CABECALHO_DYNAMO + """
try:
    OUT = executar(_doc, DocumentManager.Instance.CurrentUIApplication.Application.VersionName, DB)
""" + ERRO_DYNAMO

ENTRADA_LOTES = CABECALHO_DYNAMO + """
try:
    OUT = executar(
        _doc,
        DB,
        bool(IN[0]),
        IN[1],
        # O script abre transações próprias (uma por lote) para ver o resultado real do
        # Commit; para isso a transação do Dynamo precisa estar fechada.
        iniciar=TransactionManager.Instance.ForceCloseTransaction,
    )
""" + ERRO_DYNAMO

CONFIG_LOTES = json.dumps(
    {
        "dwg": "Arquivo Completo- BASE REVIT",
        "dwg_id": None,
        "camadas": [],
        "tipo_lote": ".LOTE",
        "tolerancia_m": 0.02,
        "area_min_m2": 40,
        "area_max_m2": 30000,
        "ignorar_topo_ids": [],
        "limite": 10,
        "modelo_id": None,
        "recusar_sobreposicao": True,
    },
    ensure_ascii=False,
)


ENTRADA_SALAS = CABECALHO_DYNAMO + """
try:
    OUT = executar(
        _doc,
        DB,
        bool(IN[0]),
        IN[1],
        iniciar=TransactionManager.Instance.ForceCloseTransaction,
    )
""" + ERRO_DYNAMO

CONFIG_SALAS = json.dumps(
    {
        "niveis": [],
        "parede_interna": "",
        "parede_externa": "",
        "externa_face_interna": True,
        "junta_max_m": 0.30,
        "sem_parede": ["patio", "pergolado", "praca", "estacionamento", "externa", "quadra descoberta"],
        "criar_ambientes": True,
        "piso_oficial": "",
        "mapa_setores": {},
    },
    ensure_ascii=False,
)


def uid():
    return str(uuid.uuid4())


def port(name, description=""):
    return {
        "Id": uid(),
        "Name": name,
        "Description": description,
        "UsingDefaultValue": False,
        "Level": 2,
        "UseLevels": False,
        "KeepListStructure": False,
    }


def node_view(node_id, name, x, y, is_output=False):
    return {
        "Id": node_id,
        "Name": name,
        "IsSetAsInput": False,
        "IsSetAsOutput": is_output,
        "Excluded": False,
        "ShowGeometry": True,
        "X": x,
        "Y": y,
    }


def input_node(kind, label, value, x, y):
    node_id = uid()
    concrete, node_type = {
        "bool": ("CoreNodeModels.Input.BoolSelector, CoreNodeModels", "BooleanInputNode"),
        "string": ("CoreNodeModels.Input.StringInput, CoreNodeModels", "StringInputNode"),
    }[kind]
    node = {
        "ConcreteType": concrete,
        "NodeType": node_type,
        "InputValue": value,
        "Id": node_id,
        "Inputs": [],
        "Outputs": [port("", kind)],
        "Replication": "Disabled",
        "Description": label,
    }
    view = dict(node_view(node_id, label, x, y), IsSetAsInput=True)
    return node, view


def graph(name, description, scripts, entrada, note, inputs=()):
    py_id, watch_id = uid(), uid()
    code = "\n\n".join((SCRIPTS / s).read_text(encoding="utf-8") for s in scripts) + entrada
    input_nodes, input_views, connectors = [], [], []
    for index, (kind, label, value) in enumerate(inputs):
        node, view = input_node(kind, label, value, 70.0, 180.0 + index * 135.0)
        input_nodes.append(node)
        input_views.append(view)
        connectors.append({"StartIndex": 0, "EndIndex": index, "Id": uid(), "Start": node["Id"], "End": py_id})
    nodes = input_nodes + [
        {
            "ConcreteType": "PythonNodeModels.PythonNode, PythonNodeModels",
            "NodeType": "PythonScriptNode",
            "Code": code,
            "Engine": "CPython3",
            "VariableInputPorts": True,
            "Id": py_id,
            "Inputs": [port("IN[%d]" % i, label) for i, (_, label, _) in enumerate(inputs)],
            "Outputs": [port("OUT", "Relatório")],
            "Replication": "Disabled",
            "Description": description,
        },
        {
            "ConcreteType": "CoreNodeModels.Watch, CoreNodeModels",
            "NodeType": "ExtensionNode",
            "Id": watch_id,
            "Inputs": [port("", "Relatório")],
            "Outputs": [port("", "")],
            "Replication": "Disabled",
            "Description": "Relatório",
        },
    ]
    return {
        "Uuid": uid(),
        "IsCustomNode": False,
        "Description": description,
        "Name": name,
        "ElementResolver": {"ResolutionMap": {}},
        "Inputs": [],
        "Outputs": [],
        "Nodes": nodes,
        "Connectors": connectors
        + [{"StartIndex": 0, "EndIndex": 0, "Id": uid(), "Start": py_id, "End": watch_id}],
        "Dependencies": [],
        "NodeLibraryDependencies": [],
        "Thumbnail": "",
        "GraphDocumentationURL": None,
        "ExtensionWorkspaceData": [],
        "Author": "TCC CTJ",
        "Linting": {"activeLinter": "None", "linterIdMap": {}},
        "Bindings": [],
        "View": {
            "Dynamo": {
                "ScaleFactor": 1.0,
                "HasRunWithoutCrash": True,
                "IsVisibleInDynamoLibrary": True,
                "Version": "3.4.0",
                "RunType": "Manual",
                "RunPeriod": 1000,
            },
            "Camera": {
                "Name": "_Background Preview",
                "EyeX": -17.0,
                "EyeY": 24.0,
                "EyeZ": 50.0,
                "LookX": 12.0,
                "LookY": -13.0,
                "LookZ": -58.0,
                "UpX": 0.0,
                "UpY": 1.0,
                "UpZ": 0.0,
            },
            "NodeViews": input_views
            + [
                node_view(py_id, name, 450.0, 200.0),
                node_view(watch_id, "Relatório", 950.0, 200.0, is_output=True),
            ],
            "Annotations": [
                {
                    "Id": uid(),
                    "Title": "TCC — EXECUÇÃO MANUAL",
                    "Description": note,
                    "Left": 60.0,
                    "Top": 35.0,
                    "Width": 720.0,
                    "Height": 105.0,
                    "FontSize": 30.0,
                    "InitialTop": 35.0,
                    "InitialHeight": 105.0,
                    "TextblockHeight": 75.0,
                    "Background": "#FFC1D676",
                    "IdList": [],
                    "IsExpanded": True,
                    "AnnotationText": note,
                    "IsSelectedIsolated": False,
                }
            ],
            "X": 0.0,
            "Y": 0.0,
            "Zoom": 1.0,
        },
    }


SPECS = (
    (
        "TCC_Inventario.dyn",
        graph(
            "TCC Inventário",
            "Somente leitura: localização, coordenadas, topografia, DWGs, vistas e tipos.",
            ["tcc_inventario.py"],
            ENTRADA_INVENTARIO,
            "Somente leitura. Clique em Run; o JSON é salvo ao lado do .rvt.",
        ),
    ),
    (
        "TCC_Lotes.dyn",
        graph(
            "TCC Lotes",
            "Lotes do DWG BASE REVIT como subdivisões das quadras (Toposolid).",
            ["tcc_geometria.py", "tcc_lotes.py"],
            ENTRADA_LOTES,
            "Rode primeiro com False (simulação). Depois True: piloto de 10 lotes. Por fim limite 0.",
            inputs=(
                ("bool", "Executar (False = simulação)", False),
                ("string", "Configuração (JSON)", CONFIG_LOTES),
            ),
        ),
    ),
    (
        "TCC_Salas.dyn",
        graph(
            "TCC Salas",
            "Pisos-sala (nome no Comentários, setor no material) → paredes, ambientes e tabela de áreas.",
            ["tcc_geometria.py", "tcc_salas.py"],
            ENTRADA_SALAS,
            "Rode primeiro com False (simulação) num pavimento: \"niveis\": [\"Térreo\"]. Depois True. Ctrl+Z desfaz tudo.",
            inputs=(
                ("bool", "Executar (False = simulação)", False),
                ("string", "Configuração (JSON)", CONFIG_SALAS),
            ),
        ),
    ),
)


def main():
    DYNAMO.mkdir(exist_ok=True)
    for filename, payload in SPECS:
        path = DYNAMO / filename
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("{}: {} bytes".format(path, path.stat().st_size))


if __name__ == "__main__":
    main()
