# -*- coding: utf-8 -*-
"""Inventário somente leitura do modelo aberto (pensado para o TERRENO - JD IPE-TCC.rvt).

Responde o que os mapas precisam saber antes de desenhar qualquer coisa:
onde o terreno está (geolocalização e coordenadas compartilhadas), qual a faixa de
cotas, quais DWGs/vínculos existem (e suas camadas) e que vistas/tipos já estão no arquivo.

Roda em pyRevit (IronPython 2.7 ou CPython) e no nó Python do Dynamo — por isso nada de
f-strings. Não abre transação: não altera o modelo.
"""

import json
import math
import os

FT_TO_M = 0.3048


def _m(value_ft):
    return round(value_ft * FT_TO_M, 3)


def _xyz(pt):
    return [_m(pt.X), _m(pt.Y), _m(pt.Z)]


def _bbox(element, to_shared):
    bb = element.get_BoundingBox(None)
    if bb is None:
        return None
    return {
        "interno_min": _xyz(bb.Min),
        "interno_max": _xyz(bb.Max),
        "compartilhado_min": _xyz(to_shared.OfPoint(bb.Min)),
        "compartilhado_max": _xyz(to_shared.OfPoint(bb.Max)),
    }


def _int_id(element_id):
    # Revit 2026 removeu ElementId.IntegerValue; .Value existe desde o 2024.
    return int(
        element_id.Value if hasattr(element_id, "Value") else element_id.IntegerValue
    )


def _name(element):
    try:
        return element.Name
    except Exception:
        return None


def _type_name(doc, element):
    type_id = element.GetTypeId()
    if type_id is None or _int_id(type_id) < 0:
        return None
    return _name(doc.GetElement(type_id))


def _localizacao(doc, DB):
    site = doc.SiteLocation
    position = doc.ActiveProjectLocation.GetProjectPosition(DB.XYZ.Zero)
    survey = DB.BasePoint.GetSurveyPoint(doc)
    base = DB.BasePoint.GetProjectBasePoint(doc)
    return {
        "local": site.PlaceName,
        "latitude_graus": round(math.degrees(site.Latitude), 7),
        "longitude_graus": round(math.degrees(site.Longitude), 7),
        "local_ativo": doc.ActiveProjectLocation.Name,
        "posicao_projeto": {
            "leste_oeste_m": _m(position.EastWest),
            "norte_sul_m": _m(position.NorthSouth),
            "elevacao_m": _m(position.Elevation),
            "angulo_norte_verdadeiro_graus": round(math.degrees(position.Angle), 6),
        },
        "ponto_levantamento": {
            "interno": _xyz(survey.Position),
            "compartilhado": _xyz(survey.SharedPosition),
        },
        "ponto_base_projeto": {
            "interno": _xyz(base.Position),
            "compartilhado": _xyz(base.SharedPosition),
        },
    }


def _coletar(doc, DB, cls=None, categoria=None):
    collector = DB.FilteredElementCollector(doc)
    if cls is not None:
        collector = collector.OfClass(cls)
    if categoria is not None:
        collector = collector.OfCategory(categoria)
    return list(collector.WhereElementIsNotElementType())


def _classe_topografia_legada(DB):
    # No CPython3 do Dynamo, subnamespaces nem sempre aparecem como atributo do módulo.
    try:
        return DB.Architecture.TopographySurface
    except AttributeError:
        from Autodesk.Revit.DB.Architecture import TopographySurface

        return TopographySurface


def _topografia(doc, DB, to_shared):
    itens = []
    classes = []
    if hasattr(DB, "Toposolid"):
        classes.append(("Toposolid", DB.Toposolid))
    classes.append(("TopographySurface", _classe_topografia_legada(DB)))
    for rotulo, cls in classes:
        for el in _coletar(doc, DB, cls=cls):
            itens.append(
                {
                    "classe": rotulo,
                    "id": _int_id(el.Id),
                    "tipo": _type_name(doc, el),
                    "caixa": _bbox(el, to_shared),
                }
            )
    return itens


def _cads(doc, DB, to_shared):
    itens = []
    for el in _coletar(doc, DB, cls=DB.ImportInstance):
        camadas = []
        if el.Category is not None:
            camadas = sorted(sub.Name for sub in el.Category.SubCategories)
        itens.append(
            {
                "id": _int_id(el.Id),
                "nome": el.Category.Name if el.Category is not None else _name(el),
                "vinculado": el.IsLinked,
                "caixa": _bbox(el, to_shared),
                "camadas": camadas,
            }
        )
    return itens


def _vinculos_revit(doc, DB):
    itens = []
    for el in _coletar(doc, DB, cls=DB.RevitLinkInstance):
        linked = el.GetLinkDocument()
        itens.append(
            {
                "id": _int_id(el.Id),
                "nome": _name(el),
                "carregado": linked is not None,
                "arquivo": linked.Title if linked is not None else None,
            }
        )
    return itens


def _niveis(doc, DB):
    niveis = [(lv.Name, _m(lv.Elevation)) for lv in _coletar(doc, DB, cls=DB.Level)]
    return [{"nome": n, "elevacao_m": e} for n, e in sorted(niveis, key=lambda t: t[1])]


def _escala(view):
    try:
        return view.Scale or None
    except Exception:
        return None


def _vistas(doc, DB):
    itens = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View):
        if v.IsTemplate:
            continue
        itens.append(
            {
                "nome": _name(v),
                "tipo": str(v.ViewType),
                "escala": _escala(v),
            }
        )
    return sorted(itens, key=lambda d: (d["tipo"], d["nome"] or ""))


def _nomes_de_tipos(doc, DB, cls):
    nomes = (_name(t) for t in DB.FilteredElementCollector(doc).OfClass(cls))
    return sorted(n for n in nomes if n)


def _estilos_de_linha(doc, DB):
    linhas = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Lines)
    return sorted(sub.Name for sub in linhas.SubCategories)


def inventariar(doc, app_version, DB):
    to_shared = doc.ActiveProjectLocation.GetTotalTransform().Inverse
    return {
        "arquivo": doc.Title,
        "caminho": doc.PathName,
        "revit": app_version,
        "localizacao": _localizacao(doc, DB),
        "niveis": _niveis(doc, DB),
        "topografia": _topografia(doc, DB, to_shared),
        "cads": _cads(doc, DB, to_shared),
        "vinculos_revit": _vinculos_revit(doc, DB),
        "vistas": _vistas(doc, DB),
        "tipos_regiao_preenchida": _nomes_de_tipos(doc, DB, DB.FilledRegionType),
        "estilos_de_linha": _estilos_de_linha(doc, DB),
        "folhas": len(list(DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet))),
    }


def caminho_saida(doc):
    pasta = os.path.dirname(doc.PathName) if doc.PathName else os.path.expanduser("~")
    base = os.path.splitext(os.path.basename(doc.PathName or doc.Title))[0]
    return os.path.join(pasta, "inventario_" + base.replace(" ", "_") + ".json")


def salvar(dados, caminho):
    texto = json.dumps(dados, indent=2, ensure_ascii=False, sort_keys=False)
    with open(caminho, "wb") as fh:
        fh.write(texto.encode("utf-8"))
    return caminho


def resumo(dados):
    loc = dados["localizacao"]
    linhas = [
        "Arquivo: %s (%s)" % (dados["arquivo"], dados["revit"]),
        "Geolocalização: %s  lat %s  lon %s"
        % (loc["local"], loc["latitude_graus"], loc["longitude_graus"]),
        "Ponto de levantamento (compartilhado): %s"
        % loc["ponto_levantamento"]["compartilhado"],
        "Ângulo para o norte verdadeiro: %s°"
        % loc["posicao_projeto"]["angulo_norte_verdadeiro_graus"],
        "Topografias: %d · CADs: %d · Vínculos Revit: %d · Níveis: %d · Vistas: %d"
        % (
            len(dados["topografia"]),
            len(dados["cads"]),
            len(dados["vinculos_revit"]),
            len(dados["niveis"]),
            len(dados["vistas"]),
        ),
    ]
    for topo in dados["topografia"]:
        caixa = topo["caixa"] or {}
        linhas.append(
            "  %s #%s: cotas %s → %s"
            % (
                topo["classe"],
                topo["id"],
                (caixa.get("compartilhado_min") or [None] * 3)[2],
                (caixa.get("compartilhado_max") or [None] * 3)[2],
            )
        )
    for cad in dados["cads"]:
        linhas.append("  CAD %s (%d camadas)" % (cad["nome"], len(cad["camadas"])))
    return "\n".join(linhas)


def executar(doc, app_version, DB):
    dados = inventariar(doc, app_version, DB)
    destino = salvar(dados, caminho_saida(doc))
    return resumo(dados) + "\n\nJSON salvo em: " + destino
