# -*- coding: utf-8 -*-
"""Modela os lotes como subdivisões do sólido topográfico, a partir do DWG "BASE REVIT".

Fluxo: linhas das camadas de lote/quadra do DWG → polígonos fechados (tcc_geometria) →
cada polígono cai numa quadra já modelada (Toposolid) → vira subdivisão dessa quadra.
Se a quadra for ela própria uma subdivisão, o lote é criado no sólido que a hospeda.

Segurança:
- `executar=False` (padrão) só simula e relata; nada muda no modelo.
- `limite` (padrão 10) cria um piloto pequeno numa mesma quadra; `0` = todos.
- Reexecutar apaga só as subdivisões marcadas com MARCA e recria.
- DWG, quadras e calçadas existentes não são alterados.
"""

import json
import os
from collections import Counter, defaultdict

try:
    from tcc_geometria import area, centroide, poligonos_de_segmentos, ponto_no_poligono
except ImportError:  # no Dynamo o tcc_geometria vem embutido no mesmo nó
    pass

FT_TO_M = 0.3048
MARCA = "TCC-AUTO-LOTE"

CONFIG_PADRAO = {
    "dwg": "Arquivo Completo- BASE REVIT",
    "dwg_id": None,
    "camadas": [],
    "tipo_lote": ".LOTE",
    "tolerancia_m": 0.02,
    "area_min_m2": 40.0,
    "area_max_m2": 30000.0,
    "ignorar_topo_ids": [],
    "limite": 10,
    "modelo_id": None,
    "area_max_modelo_m2": 2000.0,
    "recusar_sobreposicao": True,
}

# Camada de DWG com xref ligado vem como "<xref>$0$<camada>" (ex.: "Lot$0$Lot"); a regra
# olha só o último trecho, para "Lot$0$Corte" (corte dentro do xref de lotes) ficar de fora.
PREFIXOS_CAMADA = ("LOT", "QDR", "QUADRA")


# --- regras puras (testáveis sem Revit) -----------------------------------------------


def ler_config(texto):
    cfg = dict(CONFIG_PADRAO)
    if texto and texto.strip():
        try:
            cfg.update(json.loads(texto))
        except ValueError as erro:
            raise ValueError(
                "Configuração não é um JSON válido (use aspas duplas): %s" % erro
            )
    return cfg


def escolher_camadas(disponiveis, pedidas):
    if pedidas:
        alvo = set(c.upper() for c in pedidas)
        return [c for c in disponiveis if c.upper() in alvo]
    return [c for c in disponiveis if c.split("$0$")[-1].strip().upper().startswith(PREFIXOS_CAMADA)]


def poligonos_do_esboco(segmentos):
    """Todos os contornos do esboço de um sólido — vários laços (várias quadras numa
    subdivisão só) e furos (anel da calçada) entram juntos; quem decide dentro/fora é a
    regra par-ímpar em `_tamanho_se_contem`."""
    return poligonos_de_segmentos(segmentos, tolerancia=0.005)


def _dentro(topo, ponto):
    """Regra par-ímpar: dentro de um contorno e fora dos furos."""
    return sum(1 for p in topo["poligonos"] if ponto_no_poligono(ponto, p)) % 2 == 1


def _menor_contorno(topo, ponto):
    """Área do menor contorno do sólido que envolve o ponto — furo incluído — ou None.

    O furo conta de propósito: no modelo do TCC a quadra é um anel de calçada e os lotes
    ficam no furo dele.
    """
    areas = [abs(area(p)) for p in topo["poligonos"] if ponto_no_poligono(ponto, p)]
    return min(areas) if areas else None


def _ponto_na_caixa(ponto, caixa):
    return caixa[0] <= ponto[0] <= caixa[2] and caixa[1] <= ponto[1] <= caixa[3]


def _area_total(topo):
    return max(area(p) for p in topo["poligonos"])


def planejar_lotes(poligonos, topos, cfg, registro=None):
    """Decide, para cada polígono do DWG, se é lote e em qual sólido ele será subdivisão.

    `topos`: [{"id", "host_id" (None se não é subdivisão), "poligonos"}].
    O maior sólido é o terreno geral e não conta como quadra (a menos que se informe
    `ignorar_topo_ids`). Polígono que cai num sólido já do tipo do lote não é recriado.
    `registro`, se dado, recebe o destino de cada polígono.
    """
    ignorar = set(cfg["ignorar_topo_ids"])
    if not ignorar and topos:
        ignorar = {max(topos, key=_area_total)["id"]}
    zonas = [t for t in topos if t["id"] not in ignorar and t["poligonos"]]
    tipo_lote = (cfg.get("tipo_lote") or "").strip().lower()
    caixas = dict((z["id"], _caixa([z], folga=0.0)) for z in zonas)

    lotes, rejeitados = [], Counter()
    for poligono in poligonos:
        a = area(poligono)
        zona = None
        if a < cfg["area_min_m2"]:
            status = "area_pequena"
        elif a > cfg["area_max_m2"]:
            status = "area_grande"
        else:
            c = centroide(poligono)
            perto = [z for z in zonas if _ponto_na_caixa(c, caixas[z["id"]])]
            modelados = [z for z in perto if z["tipo"].strip().lower() == tipo_lote and _dentro(z, c)]
            candidatas = [(_menor_contorno(z, c), 0 if _dentro(z, c) else 1, z) for z in perto]
            candidatas = [k for k in candidatas if k[0] is not None]
            if modelados:
                # Lote modelado à mão (ou o terreno do CTJ): não recria nem sobrepõe.
                status = "ja_modelado"
                zona = min(modelados, key=lambda z: _menor_contorno(z, c))
            elif not candidatas:
                status = "fora_das_quadras"
            else:
                status = "lote"
                # Menor contorno; empate → o sólido em que o ponto está de fato (não no furo).
                zona = min(candidatas, key=lambda k: (k[0], k[1]))[2]
                lotes.append({
                    "poligono": poligono,
                    "area": round(a, 2),
                    "zona_id": zona["id"],
                    "host_id": zona["host_id"] if zona["host_id"] is not None else zona["id"],
                })
        if status != "lote":
            rejeitados[status] += 1
        if registro is not None:
            registro.append({"poligono": poligono, "status": status, "zona_id": zona["id"] if zona else None})
    return lotes, dict(rejeitados)


def escolher_modelo(topos, cfg):
    """Lote modelado à mão que serve de padrão: o de área mediana entre os `.LOTE`
    manuais de tamanho de lote (o terreno do CTJ, bem maior, fica de fora)."""
    tipo_lote = (cfg.get("tipo_lote") or "").strip().lower()
    manuais = [
        t for t in topos
        if t["tipo"].strip().lower() == tipo_lote and t.get("marca") != MARCA
    ]
    if cfg.get("modelo_id"):
        escolhidos = [t for t in manuais if t["id"] == int(cfg["modelo_id"])]
        if not escolhidos:
            raise ValueError("modelo_id %s não é um %s manual." % (cfg["modelo_id"], cfg["tipo_lote"]))
        return escolhidos[0]
    candidatos = sorted(
        (t for t in manuais if _area_total(t) <= cfg["area_max_modelo_m2"]), key=_area_total)
    return candidatos[len(candidatos) // 2] if candidatos else None


def numerar(lotes):
    """Marca Q##-L##: quadras de norte para sul, lotes em faixas de 10 m, da esquerda para a direita."""
    def chave(pontos):
        x, y = pontos
        return (-int(round(y / 10.0)), x)

    centros = dict((id(l), centroide(l["poligono"])) for l in lotes)
    por_zona = defaultdict(list)
    for l in lotes:
        por_zona[l["zona_id"]].append(l)
    def centro_da_zona(zona):
        pts = [centros[id(l)] for l in por_zona[zona]]
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

    zonas = sorted(por_zona, key=lambda z: chave(centro_da_zona(z)))
    for q, zona in enumerate(zonas, 1):
        for n, l in enumerate(sorted(por_zona[zona], key=lambda l: chave(centros[id(l)])), 1):
            l["marca"] = "Q%02d-L%02d" % (q, n)
    return lotes


def e_sobreposicao(texto):
    texto = (texto or "").lower()
    return "sobrep" in texto or "overlap" in texto


def parametros_copiaveis(DB, modelo):
    """Parâmetros de instância editáveis do lote-modelo (menos Comentários e Marca)."""
    leitura = {
        DB.StorageType.Double: lambda p: p.AsDouble(),
        DB.StorageType.Integer: lambda p: p.AsInteger(),
        DB.StorageType.String: lambda p: p.AsString(),
        DB.StorageType.ElementId: lambda p: p.AsElementId(),
    }
    ignorar = (DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS, DB.BuiltInParameter.ALL_MODEL_MARK)
    copiaveis = []
    for p in modelo.Parameters:
        definicao = p.Definition
        if p.IsReadOnly or not p.HasValue or p.StorageType not in leitura:
            continue
        if getattr(definicao, "BuiltInParameter", None) in ignorar:
            continue
        copiaveis.append({
            "definicao": definicao,
            "nome": definicao.Name,
            "valor": leitura[p.StorageType](p),
            "texto": p.AsValueString() or "",
        })
    return copiaveis


def aplicar_parametros(elemento, copiaveis):
    falhas = []
    for c in copiaveis:
        try:
            p = elemento.get_Parameter(c["definicao"])
            if p is not None and not p.IsReadOnly:
                p.Set(c["valor"])
        except Exception:
            falhas.append(c["nome"])
    return falhas


def aplicar_limite(lotes, limite):
    """Piloto: lotes agrupados por quadra, para o teste cair num lugar só."""
    ordenados = sorted(
        lotes,
        key=lambda l: (
            (l["zona_id"],) + tuple(round(v, 2) for v in centroide(l["poligono"]))
        ),
    )
    return ordenados if not limite else ordenados[: int(limite)]


# --- Revit ----------------------------------------------------------------------------


def _int_id(element_id):
    # Revit 2026 removeu ElementId.IntegerValue; .Value existe desde o 2024.
    return int(
        element_id.Value if hasattr(element_id, "Value") else element_id.IntegerValue
    )


def _nome(DB, elemento):
    """Nome de tipo/elemento: no CPython3 do Dynamo `.Name` às vezes falha em ElementType."""
    if elemento is None:
        return "?"
    for ler in (
        lambda: elemento.Name,
        lambda: DB.Element.Name.__get__(elemento),
        lambda: elemento.get_Parameter(
            DB.BuiltInParameter.ALL_MODEL_TYPE_NAME
        ).AsString(),
    ):
        try:
            valor = ler()
            if valor:
                return valor
        except Exception:
            pass
    return "?"


def _m(pt):
    return (pt.X * FT_TO_M, pt.Y * FT_TO_M)


def _pares(pontos):
    return [(_m(a), _m(b)) for a, b in zip(pontos, pontos[1:])]


def _segmentos_da_geometria(obj, DB):
    if isinstance(obj, DB.PolyLine):
        return "polilinha", _pares(list(obj.GetCoordinates()))
    if isinstance(obj, DB.Curve):
        return obj.GetType().Name.lower(), _pares(list(obj.Tessellate()))
    return "outro", []


def segmentos_do_dwg(doc, DB, instancia):
    """{camada: [segmentos em m]} e {camada: Counter(tipo)} das linhas do DWG."""
    segmentos, tipos = defaultdict(list), defaultdict(Counter)
    for item in instancia.get_Geometry(DB.Options()):
        if not isinstance(item, DB.GeometryInstance):
            continue
        for obj in item.GetInstanceGeometry():
            estilo = doc.GetElement(obj.GraphicsStyleId)
            camada = (
                estilo.GraphicsStyleCategory.Name
                if estilo is not None
                else "(sem camada)"
            )
            tipo, segs = _segmentos_da_geometria(obj, DB)
            tipos[camada][tipo] += 1
            segmentos[camada].extend(segs)
    return segmentos, tipos


def _pegada_do_topo(doc, DB, topo):
    segs = []
    sketch = doc.GetElement(topo.SketchId) if hasattr(topo, "SketchId") else None
    if sketch is not None:
        for laco in sketch.Profile:
            for curva in laco:
                segs.extend(_pares(list(curva.Tessellate())))
    if segs:
        return poligonos_do_esboco(segs)
    bb = topo.get_BoundingBox(None)
    (x0, y0), (x1, y1) = _m(bb.Min), _m(bb.Max)
    return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]


def solidos_topograficos(doc, DB):
    topos, elementos = [], {}
    for t in DB.FilteredElementCollector(doc).OfClass(DB.Toposolid):
        poligonos = _pegada_do_topo(doc, DB, t)
        if not poligonos:
            continue
        host = _int_id(t.HostTopoId)
        tipo = doc.GetElement(t.GetTypeId())
        comentario = t.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        tid = _int_id(t.Id)
        elementos[tid] = t
        topos.append(
            {
                "id": tid,
                "host_id": host if host >= 0 else None,
                "poligonos": poligonos,
                "tipo": _nome(DB, tipo),
                "marca": comentario.AsString() if comentario is not None else None,
            }
        )
    return topos, elementos


def _lista_net(DB):
    from System.Collections.Generic import List

    def converter(itens):
        lista = List[DB.CurveLoop]()
        for item in itens:
            lista.Add(item)
        return lista

    return converter


def _curve_loop(DB, poligono):
    loop = DB.CurveLoop()
    pts = [DB.XYZ(x / FT_TO_M, y / FT_TO_M, 0.0) for x, y in poligono]
    for a, b in zip(pts, pts[1:] + pts[:1]):
        loop.Append(DB.Line.CreateBound(a, b))
    return loop


# Falhas que o Revit levanta na confirmação de cada transação (preenchido pelo coletor).
_FALHAS = {"erros": [], "avisos": [], "recusar_sobreposicao": True}
_SEQUENCIA_COLETOR = [0]


def _classe_coletor(DB):
    """IFailuresPreprocessor que anota avisos (e os descarta) e erros (e desfaz o lote).

    Sem isso o Revit pode desfazer a transação em silêncio — foi o que aconteceu no
    primeiro piloto. O nome do namespace muda a cada execução porque o pythonnet do
    Dynamo não deixa redefinir a mesma classe .NET na mesma sessão.
    """

    def preprocessar(self, acessor):
        tem_erro = False
        for falha in acessor.GetFailureMessages():
            texto = falha.GetDescriptionText()
            aviso = falha.GetSeverity() == DB.FailureSeverity.Warning
            if aviso and not (_FALHAS["recusar_sobreposicao"] and e_sobreposicao(texto)):
                _FALHAS["avisos"].append(texto)
                acessor.DeleteWarning(falha)
            else:
                _FALHAS["erros"].append(texto)
                tem_erro = True
        if tem_erro:
            return DB.FailureProcessingResult.ProceedWithRollBack
        return DB.FailureProcessingResult.Continue

    _SEQUENCIA_COLETOR[0] += 1
    namespace = "TCC.Lotes.Coletor%d_%d" % (os.getpid(), _SEQUENCIA_COLETOR[0])
    return type("ColetorFalhas", (DB.IFailuresPreprocessor,), {
        "__namespace__": namespace,
        "PreprocessFailures": preprocessar,
    })


class _TransacaoRevit(object):
    """Transação de verdade (não SubTransaction): o resultado do Commit é o do modelo."""

    coletor = None

    def __init__(self, doc, DB, nome):
        self.DB = DB
        self.t = DB.Transaction(doc, nome)
        if _TransacaoRevit.coletor is not None:
            opcoes = self.t.GetFailureHandlingOptions()
            opcoes.SetFailuresPreprocessor(_TransacaoRevit.coletor)
            opcoes.SetClearAfterRollback(True)
            self.t.SetFailureHandlingOptions(opcoes)

    def iniciar(self):
        del _FALHAS["erros"][:]
        del _FALHAS["avisos"][:]
        self.t.Start()

    def confirmar(self):
        status = self.t.Commit()
        ok = status == self.DB.TransactionStatus.Committed
        erros = list(_FALHAS["erros"])
        if not ok and not erros:
            erros = ["status %s, sem mensagem" % status]
        return ok, erros, list(_FALHAS["avisos"])

    def desfazer(self):
        if self.t.HasStarted() and not self.t.HasEnded():
            self.t.RollBack()


def _fabrica_transacao(doc, DB):
    if _TransacaoRevit.coletor is None:
        try:
            _TransacaoRevit.coletor = _classe_coletor(DB)()
        except Exception:
            _TransacaoRevit.coletor = None  # sem coletor ainda dá para ler o status do Commit
    return lambda nome: _TransacaoRevit(doc, DB, nome)


def criar_lotes(doc, DB, lotes, hosts, tipo_id, lista=None, nova_transacao=None, parametros=()):
    """Uma transação por lote: o Revit recusar um lote desfaz só ele, com o motivo."""
    lista = lista or _lista_net(DB)
    nova_transacao = nova_transacao or _fabrica_transacao(doc, DB)
    criados, erros, ids, avisos = 0, [], [], Counter()
    for lote in lotes:
        descricao = "%s quadra %s / %.0f m²" % (lote.get("marca", ""), lote["zona_id"], lote.get("area", 0))
        transacao = nova_transacao("TCC: lote")
        transacao.iniciar()
        try:
            host = hosts[lote["host_id"]]
            perfis = lista([_curve_loop(DB, lote["poligono"])])
            if tipo_id is not None:
                novo = host.CreateSubDivision(doc, tipo_id, perfis)
            else:
                novo = host.CreateSubDivision(doc, perfis)
            novo.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS).Set(MARCA)
            if lote.get("marca"):
                novo.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK).Set(lote["marca"])
            for nome in aplicar_parametros(novo, parametros):
                avisos["parâmetro não copiado: " + nome] += 1
        except Exception as erro:
            transacao.desfazer()
            erros.append("%s: %s" % (descricao, erro))
            continue
        ok, msgs_erro, msgs_aviso = transacao.confirmar()
        for aviso in msgs_aviso:
            avisos[aviso] += 1
        if ok:
            criados += 1
            ids.append(_int_id(novo.Id))
        else:
            erros.append("%s: Revit desfez: %s" % (descricao, " | ".join(msgs_erro)))
    return {"criados": criados, "erros": erros, "ids": ids, "avisos": dict(avisos)}


def _apagar_marcados(doc, DB, topos, elementos):
    from System.Collections.Generic import List

    ids = List[DB.ElementId]()
    for t in topos:
        if t["marca"] == MARCA:
            ids.Add(elementos[t["id"]].Id)
    if ids.Count:
        transacao = _fabrica_transacao(doc, DB)("TCC: apagar lotes anteriores")
        transacao.iniciar()
        doc.Delete(ids)
        ok, erros, _ = transacao.confirmar()
        if not ok:
            raise RuntimeError("Revit não deixou apagar os lotes anteriores: " + " | ".join(erros))
    return ids.Count


def _conferir_no_modelo(doc, DB):
    """Relê o modelo depois das transações: o que existe de fato com a MARCA."""
    marcados = []
    for t in DB.FilteredElementCollector(doc).OfClass(DB.Toposolid):
        comentario = t.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if comentario is not None and comentario.AsString() == MARCA:
            marcados.append(t)
    zs = []
    for t in marcados:
        bb = t.get_BoundingBox(None)
        if bb is not None:
            zs += [bb.Min.Z * FT_TO_M, bb.Max.Z * FT_TO_M]
    texto = "Conferência no modelo: %d lotes %s existem agora" % (len(marcados), MARCA)
    if marcados:
        texto += " · IDs: %s%s" % (", ".join(str(_int_id(t.Id)) for t in marcados[:12]),
                                   " …" if len(marcados) > 12 else "")
    if zs:
        texto += " · cotas %.1f a %.1f m" % (min(zs), max(zs))
    return texto


def _tipo_por_nome(doc, DB, nome):
    tipos = [
        (_nome(DB, t), t)
        for t in DB.FilteredElementCollector(doc).OfClass(DB.ToposolidType)
    ]
    nomes = sorted(n for n, _ in tipos)
    if not nome:
        return None, nomes
    for n, t in tipos:
        if n.strip().lower() == nome.strip().lower():
            return t.Id, nomes
    raise ValueError(
        "Tipo de topografia '%s' não existe. Disponíveis: %s"
        % (nome, ", ".join(sorted(nomes)))
    )


def _candidatos_dwg(doc, DB, cfg):
    candidatos = [
        i
        for i in DB.FilteredElementCollector(doc).OfClass(DB.ImportInstance)
        if i.Category is not None and cfg["dwg"].lower() in i.Category.Name.lower()
    ]
    if cfg["dwg_id"]:
        candidatos = [i for i in candidatos if _int_id(i.Id) == int(cfg["dwg_id"])]
    if not candidatos:
        raise ValueError("Nenhum DWG com '%s' no nome (ou dwg_id não confere)." % cfg["dwg"])
    return candidatos


def _analisar_dwg(doc, DB, instancia, cfg, caixa):
    por_camada, tipos = segmentos_do_dwg(doc, DB, instancia)
    camadas = escolher_camadas(sorted(por_camada), cfg["camadas"])
    segmentos = [s for c in camadas for s in por_camada[c]]
    return {
        "instancia": instancia,
        "por_camada": por_camada,
        "tipos": tipos,
        "camadas": camadas,
        "segmentos": segmentos,
        "dentro": [s for s in segmentos if _dentro_da_caixa(s, caixa)],
    }


def _descrever_analise(analise):
    texto = "#%s: %d de %d segmentos sobre os sólidos" % (
        _int_id(analise["instancia"].Id), len(analise["dentro"]), len(analise["segmentos"]))
    if analise["segmentos"]:
        xs = [x for seg in analise["segmentos"] for x, _ in seg]
        ys = [y for seg in analise["segmentos"] for _, y in seg]
        texto += " · linhas em x %.0f a %.0f · y %.0f a %.0f" % (min(xs), max(xs), min(ys), max(ys))
    return texto


def _caixa(topos, folga=1.0):
    xs = [x for t in topos for p in t["poligonos"] for x, _ in p]
    ys = [y for t in topos for p in t["poligonos"] for _, y in p]
    return min(xs) - folga, min(ys) - folga, max(xs) + folga, max(ys) + folga


def _dentro_da_caixa(seg, caixa):
    (x1, y1), (x2, y2) = seg
    x0, y0, xf, yf = caixa
    return (
        max(x1, x2) >= x0
        and min(x1, x2) <= xf
        and max(y1, y2) >= y0
        and min(y1, y2) <= yf
    )


def _salvar_lotes(doc, lotes, topos, registro):
    """Lotes + diagnóstico (sólidos e destino de cada polígono do DWG) num JSON ao lado do .rvt."""
    pasta = os.path.dirname(doc.PathName) if doc.PathName else os.path.expanduser("~")
    caminho = os.path.join(pasta, "lotes_" + doc.Title.replace(" ", "_") + ".json")
    dados = {
        "unidade": "m (coordenadas internas do modelo)",
        "lotes": lotes,
        "solidos": [dict((k, t[k]) for k in ("id", "host_id", "tipo", "poligonos")) for t in topos],
        "poligonos_dwg": registro,
    }
    with open(caminho, "wb") as fh:
        fh.write(json.dumps(dados, ensure_ascii=False).encode("utf-8"))
    return caminho


def _zonas_por_tipo(topos, lotes):
    lotes_por_zona = Counter(l["zona_id"] for l in lotes)
    linhas = []
    for tipo in sorted(set(t["tipo"] for t in topos)):
        do_tipo = [t for t in topos if t["tipo"] == tipo]
        xs = [x for t in do_tipo for p in t["poligonos"] for x, _ in p]
        ys = [y for t in do_tipo for p in t["poligonos"] for _, y in p]
        linhas.append("  %s: %d sólidos, %d contornos, %d lotes · x %.0f a %.0f · y %.0f a %.0f" % (
            tipo, len(do_tipo), sum(len(t["poligonos"]) for t in do_tipo),
            sum(lotes_por_zona[t["id"]] for t in do_tipo), min(xs), max(xs), min(ys), max(ys)))
    return linhas


def executar(doc, DB, executar_criacao, config_texto, iniciar=None, concluir=None):
    cfg = ler_config(config_texto)
    linhas = [
        "LOTES — "
        + ("EXECUÇÃO" if executar_criacao else "SIMULAÇÃO (nada foi alterado)"),
        "",
    ]

    topos, elementos = solidos_topograficos(doc, DB)
    existentes = [t for t in topos if t["marca"] == MARCA]
    topos_base = [t for t in topos if t["marca"] != MARCA]
    caixa = _caixa(topos_base)

    # Pode haver mais de uma cópia do DWG (ex.: "BASE REVIT.dwg (2)"); vale a que cai
    # sobre as quadras modeladas.
    analises = [_analisar_dwg(doc, DB, inst, cfg, caixa) for inst in _candidatos_dwg(doc, DB, cfg)]
    escolhida = max(analises, key=lambda a: len(a["dentro"]))
    dwg = escolhida["instancia"]
    linhas.append("DWG usado: %s #%s" % (dwg.Category.Name, _int_id(dwg.Id)))
    if len(analises) > 1 or not escolhida["dentro"]:
        for analise in analises:
            linhas.append("  " + _descrever_analise(analise))

    por_camada, tipos, camadas = escolhida["por_camada"], escolhida["tipos"], escolhida["camadas"]
    linhas.append("")
    linhas.append("Camadas do DWG ([x] = usada):")
    for nome in sorted(por_camada, key=lambda n: n.upper()):
        contagem = ", ".join("%s %d" % kv for kv in sorted(tipos[nome].items()))
        linhas.append(
            "  [%s] %s — %d segmentos (%s)"
            % ("x" if nome in camadas else " ", nome, len(por_camada[nome]), contagem)
        )
    if not camadas:
        linhas.append("")
        linhas.append('Nenhuma camada escolhida. Informe "camadas" no JSON com os nomes acima.')
        return "\n".join(linhas)
    if not escolhida["dentro"]:
        linhas += [
            "",
            "Nenhuma linha das camadas escolhidas cai sobre os sólidos topográficos.",
            "Sólidos ocupam: x %.0f a %.0f · y %.0f a %.0f (m, coordenadas internas)" % (
                caixa[0], caixa[2], caixa[1], caixa[3]),
            "Compare com as posições do DWG acima: ele foi movido em relação às quadras?",
        ]
        return "\n".join(linhas)

    segmentos = escolhida["dentro"]
    poligonos = poligonos_de_segmentos(segmentos, tolerancia=cfg["tolerancia_m"])
    registro = []
    lotes, rejeitados = planejar_lotes(poligonos, topos_base, cfg, registro)
    numerar(lotes)

    hosts = Counter(t["host_id"] is None for t in topos_base)
    por_zona = Counter(l["zona_id"] for l in lotes)
    linhas += [
        "",
        "Sólidos topográficos: %d (%d independentes, %d subdivisões)"
        % (len(topos_base), hosts[True], hosts[False]),
        "  tipos em uso: %s"
        % ", ".join(
            "%s (%d)" % kv
            for kv in Counter(t["tipo"] for t in topos_base).most_common()
        ),
        "Segmentos usados (dentro da área modelada): %d" % len(segmentos),
        "Polígonos fechados encontrados: %d" % len(poligonos),
        "Lotes aceitos: %d em %d quadras · rejeitados: %s"
        % (len(lotes), len(por_zona), rejeitados or "nenhum"),
        "  quadras com mais lotes: %s"
        % ", ".join("#%s=%d" % kv for kv in por_zona.most_common(8)),
        "Lotes já criados por este script: %d%s" % (
            len(existentes), " (IDs: %s)" % ", ".join(str(t["id"]) for t in existentes[:12]) if existentes else ""),
        "Zonas por tipo:",
    ] + _zonas_por_tipo(topos_base, lotes) + [
        "Lotes e diagnóstico salvos em: %s" % _salvar_lotes(doc, lotes, topos_base, registro),
    ]

    tipo_id, tipos_disponiveis = _tipo_por_nome(doc, DB, cfg["tipo_lote"])
    linhas.append(
        "Tipo do lote: %s · disponíveis: %s"
        % (cfg["tipo_lote"] or "padrão", ", ".join(tipos_disponiveis))
    )

    modelo = escolher_modelo(topos_base, cfg)
    parametros = parametros_copiaveis(DB, elementos[modelo["id"]]) if modelo else []
    if modelo:
        linhas.append("Lote-modelo (seus .LOTE manuais): #%s, %.0f m² — troque com \"modelo_id\"" % (
            modelo["id"], _area_total(modelo)))
        linhas.append("  parâmetros que serão copiados: %s" % (
            "; ".join("%s = %s" % (c["nome"], c["texto"] or c["valor"]) for c in parametros) or "nenhum editável"))
    else:
        linhas.append("Lote-modelo: nenhum %s manual encontrado — lotes saem com o padrão do Revit." % cfg["tipo_lote"])
    linhas.append("Sobreposição com outra subdivisão: %s" % (
        "lote recusado" if cfg["recusar_sobreposicao"] else "só aviso"))
    _FALHAS["recusar_sobreposicao"] = bool(cfg["recusar_sobreposicao"])

    escolhidos = aplicar_limite(lotes, cfg["limite"])
    if not executar_criacao:
        linhas += [
            "",
            "Com Executar = True seriam criados %d lotes%s."
            % (
                len(escolhidos),
                ' (piloto; "limite": 0 cria todos)' if cfg["limite"] else "",
            ),
        ]
        return "\n".join(linhas)

    if iniciar:
        iniciar()  # no Dynamo: fecha a transação dele para usarmos as nossas
    grupo = DB.TransactionGroup(doc, "TCC: lotes")
    grupo.Start()
    try:
        apagados = _apagar_marcados(doc, DB, existentes, elementos)
        resultado = criar_lotes(doc, DB, escolhidos, elementos, tipo_id, parametros=parametros)
    finally:
        grupo.Assimilate()  # um único "Desfazer" para a execução inteira
        if concluir:
            concluir()
    linhas += [
        "",
        "Apagados (execução anterior): %d" % apagados,
        "Criados e confirmados pelo Revit: %d · Recusados: %d" % (resultado["criados"], len(resultado["erros"])),
    ]
    linhas += ["  " + e for e in resultado["erros"][:20]]
    if resultado["avisos"]:
        linhas.append("Avisos do Revit:")
        linhas += ["  %dx %s" % (n, texto) for texto, n in sorted(resultado["avisos"].items(), key=lambda kv: -kv[1])]
    linhas += ["", _conferir_no_modelo(doc, DB)]
    return "\n".join(linhas)
