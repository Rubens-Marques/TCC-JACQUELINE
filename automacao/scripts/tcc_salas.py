# -*- coding: utf-8 -*-
"""Salas desenhadas como pisos → paredes, ambientes (Rooms), pisos oficiais e tabela de áreas.

Como a Jacqueline modela: cada sala é um **piso** no seu pavimento, com o nome da sala no
parâmetro Comentários e o setor no material do piso. O script lê esses pisos e:

1. levanta as **paredes** nas bordas das salas, sem duplicar a parede entre duas salas
   vizinhas (borda compartilhada = 1 parede interna; borda solta = parede externa);
2. cria um **ambiente** (Room) em cada sala, com Nome = comentário e Departamento = setor
   — é o que alimenta planta colorida por setor, etiquetas e tabela de áreas;
3. opcionalmente cria o **piso oficial** de cada sala com o tipo escolhido;
4. salva `salas_<arquivo>.csv` (pavimento; sala; setor; área) ao lado do .rvt — base da
   tabela do programa de necessidades.

Segurança:
- `executar=False` (padrão) só simula e relata; nada muda no modelo.
- Tudo o que o script cria leva o comentário MARCA. Reexecutar apaga só isso e recria
  (portas/janelas hospedadas nessas paredes somem junto — rode antes de pôr esquadrias).
- Os pisos-sala originais não são alterados.

Compatível com Python 2.7 (IronPython/pyRevit) e 3 (Dynamo CPython3).
"""

import csv
import io
import json
import math
import os
from collections import Counter, defaultdict

try:
    from tcc_geometria import area, centroide, ponto_no_poligono
except ImportError:  # no Dynamo o tcc_geometria vem embutido no mesmo nó
    pass

FT_TO_M = 0.3048
MARCA = "TCC-AUTO-SALAS"

CONFIG_PADRAO = {
    "niveis": [],
    "parede_interna": "parede externa 15cm_growarq",
    "parede_externa": "parede externa 15cm_growarq",
    "altura_m": 3.0,
    "ate_nivel_acima": False,
    "unir_mesmo_nome": True,
    "externa_face_interna": True,
    "junta_max_m": 0.30,
    "sem_parede": ["patio", "pergolado", "praca", "estacionamento", "externa", "quadra descoberta"],
    "criar_paredes": True,
    "criar_ambientes": False,
    "salvar_tabela": False,
    "piso_oficial": "laje de concreto 10cm_growarq",
    "piso_por_setor": {},
    "setor_de": "material",
    "mapa_setores": {},
}

# Trechos de parede menores que isso são sobra de arredondamento, não parede.
COMPRIMENTO_MIN_M = 0.05
# Bordas com direções até este ângulo são tratadas como paralelas (desenho à mão).
ANGULO_TOL_RAD = math.radians(0.5)
EPS_M = 0.01


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


def _sem_acento(texto):
    trocas = {"á": "a", "à": "a", "â": "a", "ã": "a", "é": "e", "ê": "e", "í": "i",
              "ó": "o", "ô": "o", "õ": "o", "ú": "u", "ç": "c"}
    return "".join(trocas.get(c, c) for c in (texto or "").strip().lower())


def sem_parede(nome, padroes):
    """Sala aberta (pátio, pergolado…) não ganha parede: o trecho vira borda de quem encosta."""
    alvo = _sem_acento(nome)
    return any(_sem_acento(p) and _sem_acento(p) in alvo for p in padroes)


def nome_setor(material, tipo, cfg):
    bruto = tipo if cfg.get("setor_de") == "tipo" else material
    bruto = (bruto or "").strip()
    return cfg.get("mapa_setores", {}).get(bruto, bruto) or "(sem setor)"


def area_salas(lacos):
    """Área de uma sala com furos (shafts): maior contorno menos os demais."""
    areas = sorted((abs(area(l)) for l in lacos if len(l) >= 3), reverse=True)
    if not areas:
        return 0.0
    return areas[0] - sum(areas[1:])


def dentro_da_sala(ponto, lacos):
    return sum(1 for l in lacos if ponto_no_poligono(ponto, l)) % 2 == 1


def ponto_interno(lacos):
    """Ponto garantidamente dentro da sala (o centroide falha em L e em salas com furo)."""
    externo = max(lacos, key=lambda l: abs(area(l)))
    c = centroide(externo)
    if dentro_da_sala(c, lacos):
        return c
    xs = [p[0] for p in externo]
    ys = [p[1] for p in externo]
    # Varre linhas horizontais e pega o meio do trecho interno mais largo.
    melhor, largura = None, -1.0
    for k in range(1, 40):
        y = min(ys) + (max(ys) - min(ys)) * k / 40.0
        cortes = []
        for l in lacos:
            for i in range(len(l)):
                (x1, y1), (x2, y2) = l[i], l[(i + 1) % len(l)]
                if (y1 > y) != (y2 > y):
                    cortes.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        cortes.sort()
        for a, b in zip(cortes[::2], cortes[1::2]):
            if b - a > largura:
                melhor, largura = ((a + b) / 2.0, y), b - a
    return melhor or c


def _bordas(sala):
    for laco in sala["lacos"]:
        n = len(laco)
        for i in range(n):
            a, b = laco[i], laco[(i + 1) % n]
            if math.hypot(b[0] - a[0], b[1] - a[1]) > EPS_M:
                yield a, b


def _angulo(a, b):
    t = math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi
    return 0.0 if t > math.pi - ANGULO_TOL_RAD else t


class _Uniao(object):
    def __init__(self, n):
        self.pai = list(range(n))

    def raiz(self, i):
        while self.pai[i] != i:
            self.pai[i] = self.pai[self.pai[i]]
            i = self.pai[i]
        return i

    def unir(self, i, j):
        self.pai[self.raiz(i)] = self.raiz(j)


def planejar_paredes(salas, junta_max_m=0.30, unir_mesmo_nome=False):
    """Paredes de um pavimento a partir das bordas das salas.

    `salas`: [{"id", "lacos": [[(x, y), ...]], "sem_parede": bool}] em metros.
    Bordas paralelas a até `junta_max_m` uma da outra, e que se sobrepõem, são a mesma
    parede — cobre os dois jeitos de desenhar: pisos encostados (borda comum) ou pisos
    com o vão da parede entre eles (a parede vai no meio do vão).

    `unir_mesmo_nome`: pisos vizinhos com o mesmo "nome" são pedaços da mesma sala (ex.:
    circulação desenhada em dois pisos) — a emenda entre eles não vira parede.

    Devolve [{"a", "b", "tipo": "interna"|"externa", "salas": [ids], "fora": (nx, ny)|None}].
    `fora` (só nas externas) aponta para o lado de fora da sala.
    """
    bordas = []
    for sala in salas:
        if sala.get("sem_parede"):
            continue
        for a, b in _bordas(sala):
            bordas.append({"a": a, "b": b, "sala": sala["id"], "ang": _angulo(a, b)})

    # 1) grupos de direção
    grupos = []
    for borda in sorted(bordas, key=lambda x: x["ang"]):
        if grupos and abs(borda["ang"] - grupos[-1][0]["ang"]) <= ANGULO_TOL_RAD:
            grupos[-1].append(borda)
        else:
            grupos.append([borda])

    paredes = []
    por_id = dict((s["id"], s) for s in salas)
    nomes = dict((s["id"], _chave(s.get("nome") or str(s["id"]))) for s in salas)
    for grupo in grupos:
        t = grupo[0]["ang"]
        u = (math.cos(t), math.sin(t))
        n = (-u[1], u[0])
        for borda in grupo:
            a, b = borda["a"], borda["b"]
            borda["d"] = (a[0] * n[0] + a[1] * n[1] + b[0] * n[0] + b[1] * n[1]) / 2.0
            s0, s1 = a[0] * u[0] + a[1] * u[1], b[0] * u[0] + b[1] * u[1]
            borda["s"] = (min(s0, s1), max(s0, s1))

        # 2) mesma linha de parede = paralelas próximas que se sobrepõem ou se tocam
        uniao = _Uniao(len(grupo))
        ordem = sorted(range(len(grupo)), key=lambda i: grupo[i]["d"])
        for p, i in enumerate(ordem):
            for j in ordem[p + 1:]:
                if grupo[j]["d"] - grupo[i]["d"] > junta_max_m:
                    break
                (i0, i1), (j0, j1) = grupo[i]["s"], grupo[j]["s"]
                if min(i1, j1) - max(i0, j0) >= -EPS_M:
                    uniao.unir(i, j)
        linhas = defaultdict(list)
        for i in range(len(grupo)):
            linhas[uniao.raiz(i)].append(grupo[i])

        # 3) em cada linha: quebra nos extremos e conta quantas salas cobrem cada trecho
        for membros in linhas.values():
            peso = sum(m["s"][1] - m["s"][0] for m in membros)
            d = sum(m["d"] * (m["s"][1] - m["s"][0]) for m in membros) / peso
            marcos = sorted(set(round(v, 6) for m in membros for v in m["s"]))
            trechos = []
            for p, q in zip(marcos, marcos[1:]):
                if q - p <= EPS_M:
                    continue
                meio = (p + q) / 2.0
                cobrem = [m for m in membros if m["s"][0] - EPS_M <= meio <= m["s"][1] + EPS_M]
                donos = sorted(set(m["sala"] for m in cobrem), key=str)
                if not donos:
                    continue
                if unir_mesmo_nome and len(donos) > 1 and len(set(nomes[d] for d in donos)) == 1:
                    continue  # emenda entre pedaços da mesma sala
                tipo = "interna" if len(donos) > 1 else "externa"
                fora = None
                if tipo == "externa":
                    # testa a 5 cm da própria borda da sala, dos dois lados
                    m = cobrem[0]
                    x, y = u[0] * meio + n[0] * (m["d"] + 0.05), u[1] * meio + n[1] * (m["d"] + 0.05)
                    fora = (-n[0], -n[1]) if dentro_da_sala((x, y), por_id[m["sala"]]["lacos"]) else n
                # Une trechos seguidos do mesmo tipo; externa só se a sala está do mesmo lado.
                if trechos and trechos[-1]["tipo"] == tipo and abs(trechos[-1]["q"] - p) <= EPS_M \
                        and trechos[-1]["fora"] == fora:
                    trechos[-1]["q"] = q
                    trechos[-1]["salas"] = sorted(set(trechos[-1]["salas"]) | set(donos), key=str)
                else:
                    trechos.append({"p": p, "q": q, "tipo": tipo, "salas": donos, "fora": fora})

            for tr in trechos:
                if tr["q"] - tr["p"] < COMPRIMENTO_MIN_M:
                    continue
                a = (u[0] * tr["p"] + n[0] * d, u[1] * tr["p"] + n[1] * d)
                b = (u[0] * tr["q"] + n[0] * d, u[1] * tr["q"] + n[1] * d)
                paredes.append({"a": a, "b": b, "tipo": tr["tipo"], "salas": tr["salas"], "fora": tr["fora"]})
    return paredes


def deslocar_externa(parede, largura_m):
    """Empurra a parede externa para fora em meia espessura: a face interna fica na borda
    do piso, e a sala mantém a área desenhada."""
    nx, ny = parede["fora"]
    k = largura_m / 2.0
    return (
        (parede["a"][0] + nx * k, parede["a"][1] + ny * k),
        (parede["b"][0] + nx * k, parede["b"][1] + ny * k),
    )


def resumo_setores(salas):
    """[(setor, n_salas, área m²)] em ordem de área — o programa de necessidades."""
    soma, conta = defaultdict(float), Counter()
    for s in salas:
        soma[s["setor"]] += s["area"]
        conta[s["setor"]] += 1
    return sorted(((k, conta[k], soma[k]) for k in soma), key=lambda x: -x[2])


def problemas_das_salas(salas):
    """Avisos de desenho que viram parede errada se não forem corrigidos antes."""
    avisos = []
    nomes = Counter((s["nivel"], s["nome"].strip().lower()) for s in salas if s["nome"])
    for (nivel, nome), n in sorted(nomes.items()):
        if n > 1:
            avisos.append("%s: '%s' aparece em %d pisos (ok se for proposital, ex.: 2 salas de aula iguais)" % (nivel, nome, n))
    for s in salas:
        if s["area"] < 1.0:
            avisos.append("%s: sala '%s' com %.2f m² — piso duplicado ou desenho errado?" % (s["nivel"], s["nome"], s["area"]))
    return avisos


def tabela_csv(salas):
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\n")
    escritor.writerow(["pavimento", "sala", "setor", "area_m2", "piso_id"])
    for s in sorted(salas, key=lambda s: (s["elev"], s["setor"], s["nome"])):
        escritor.writerow([s["nivel"], s["nome"], s["setor"], ("%.2f" % s["area"]).replace(".", ","), s["id"]])
    return saida.getvalue()


# --- leitura do Revit -----------------------------------------------------------------


def _int_id(element_id):
    # Revit 2026 removeu ElementId.IntegerValue; .Value existe desde o 2024.
    return int(
        element_id.Value if hasattr(element_id, "Value") else element_id.IntegerValue
    )


def _nome(DB, elemento):
    """Nome de tipo/elemento: no CPython3 do Dynamo `.Name` às vezes falha em ElementType."""
    if elemento is None:
        return ""
    for ler in (
        lambda: elemento.Name,
        lambda: DB.Element.Name.__get__(elemento),
        lambda: elemento.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString(),
    ):
        try:
            valor = ler()
            if valor:
                return valor
        except Exception:
            pass
    return ""


def _comentario(DB, elemento):
    p = elemento.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    return (p.AsString() or "").strip() if p is not None else ""


def _marcar(DB, elemento, texto=MARCA):
    p = elemento.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if p is not None and not p.IsReadOnly:
        p.Set(texto)


def _material_do_piso(doc, DB, piso):
    """Material pintado (ferramenta Pintar) tem prioridade; senão, 1ª camada do tipo."""
    try:
        pintados = list(piso.GetMaterialIds(True))
    except Exception:
        pintados = []
    if pintados:
        return _nome(DB, doc.GetElement(pintados[0]))
    tipo = doc.GetElement(piso.GetTypeId())
    estrutura = tipo.GetCompoundStructure() if tipo is not None else None
    if estrutura is not None:
        for camada in estrutura.GetLayers():
            if _int_id(camada.MaterialId) > 0:
                return _nome(DB, doc.GetElement(camada.MaterialId))
    return ""


def _lacos_do_piso(doc, DB, piso):
    sketch = doc.GetElement(piso.SketchId) if hasattr(piso, "SketchId") else None
    lacos, curvas = [], 0
    if sketch is None:
        return lacos, curvas
    for arr in sketch.Profile:
        pontos = []
        for curva in arr:
            if not isinstance(curva, DB.Line):
                curvas += 1
            pts = list(curva.Tessellate())
            pontos.extend((p.X * FT_TO_M, p.Y * FT_TO_M) for p in pts[:-1])
        if len(pontos) >= 3:
            lacos.append(pontos)
    return lacos, curvas


def ler_salas(doc, DB, cfg):
    """Pisos com comentário = salas. Devolve (salas, pisos_sem_nome, bordas_curvas)."""
    salas, sem_nome, curvas = [], 0, 0
    filtro = set(_sem_acento(n) for n in cfg["niveis"])
    for piso in DB.FilteredElementCollector(doc).OfClass(DB.Floor).WhereElementIsNotElementType():
        nome = _comentario(DB, piso)
        if nome == MARCA:
            continue  # piso oficial criado por este script
        nivel = doc.GetElement(piso.LevelId)
        if nivel is None or (filtro and _sem_acento(nivel.Name) not in filtro):
            continue
        if not nome:
            sem_nome += 1
            continue
        lacos, c = _lacos_do_piso(doc, DB, piso)
        if not lacos:
            continue
        curvas += c
        tipo = _nome(DB, doc.GetElement(piso.GetTypeId()))
        salas.append({
            "id": _int_id(piso.Id),
            "nome": nome,
            "setor": nome_setor(_material_do_piso(doc, DB, piso), tipo, cfg),
            "tipo_piso": tipo,
            "nivel": nivel.Name,
            "nivel_id": nivel.Id,
            "elev": nivel.Elevation,
            "lacos": lacos,
            "area": area_salas(lacos),
            "sem_parede": sem_parede(nome, cfg["sem_parede"]),
        })
    return salas, sem_nome, curvas


def _tipos(doc, DB, classe, filtro=None):
    tipos = [t for t in DB.FilteredElementCollector(doc).OfClass(classe) if filtro is None or filtro(t)]
    return dict((_nome(DB, t), t) for t in tipos)


def _chave(nome):
    """Nome de tipo comparado sem caixa, acento e espaços sobrando."""
    return " ".join(_sem_acento(nome).split())


def _escolher(tipos, nome):
    if nome:
        achados = [t for n, t in tipos.items() if _chave(n) == _chave(nome)]
        return achados[0] if achados else None
    return tipos[sorted(tipos)[0]] if tipos else None


def _nivel_acima(doc, DB, elev):
    acima = [n for n in DB.FilteredElementCollector(doc).OfClass(DB.Level) if n.Elevation > elev + 1.0]
    return min(acima, key=lambda n: n.Elevation) if acima else None


def _marcados(doc, DB):
    achados = []
    for classe in (DB.Wall, DB.Floor):
        for e in DB.FilteredElementCollector(doc).OfClass(classe).WhereElementIsNotElementType():
            if _comentario(DB, e) == MARCA:
                achados.append(e.Id)
    for e in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_Rooms):
        if _comentario(DB, e) == MARCA:
            achados.append(e.Id)
    return achados


# --- falhas do Revit (mesmo padrão do TCC_Lotes) -------------------------------------

_FALHAS = {"erros": [], "avisos": []}
_SEQUENCIA = [0]


def _classe_coletor(DB):
    """Descarta avisos (anotando) e desfaz o pavimento se houver erro de verdade."""

    def preprocessar(self, acessor):
        tem_erro = False
        for falha in acessor.GetFailureMessages():
            texto = falha.GetDescriptionText()
            if falha.GetSeverity() == DB.FailureSeverity.Warning:
                _FALHAS["avisos"].append(texto)
                acessor.DeleteWarning(falha)
            else:
                _FALHAS["erros"].append(texto)
                tem_erro = True
        if tem_erro:
            return DB.FailureProcessingResult.ProceedWithRollBack
        return DB.FailureProcessingResult.Continue

    _SEQUENCIA[0] += 1
    namespace = "TCC.Salas.Coletor%d_%d" % (os.getpid(), _SEQUENCIA[0])
    return type("ColetorFalhasSalas", (DB.IFailuresPreprocessor,), {
        "__namespace__": namespace,
        "PreprocessFailures": preprocessar,
    })


def _transacao(doc, DB, nome, coletor):
    t = DB.Transaction(doc, nome)
    if coletor is not None:
        opcoes = t.GetFailureHandlingOptions()
        opcoes.SetFailuresPreprocessor(coletor)
        opcoes.SetClearAfterRollback(True)
        t.SetFailureHandlingOptions(opcoes)
    return t


def _rodar(doc, DB, nome, coletor, acao):
    """Executa `acao()` numa transação; devolve (ok, resultado, erros)."""
    del _FALHAS["erros"][:]
    t = _transacao(doc, DB, nome, coletor)
    t.Start()
    try:
        resultado = acao()
    except Exception as erro:
        t.RollBack()
        return False, None, [str(erro)]
    ok = t.Commit() == DB.TransactionStatus.Committed
    return ok, resultado, list(_FALHAS["erros"])


# --- criação --------------------------------------------------------------------------


def _xyz(DB, p, z):
    return DB.XYZ(p[0] / FT_TO_M, p[1] / FT_TO_M, z)


def _criar_paredes(doc, DB, paredes, nivel, tipos, cfg):
    acima = _nivel_acima(doc, DB, nivel.Elevation) if cfg["ate_nivel_acima"] else None
    altura = (acima.Elevation - nivel.Elevation) if acima is not None else cfg["altura_m"] / FT_TO_M
    criadas = 0
    for p in paredes:
        tipo = tipos[p["tipo"]]
        a, b = p["a"], p["b"]
        if p["tipo"] == "externa" and cfg["externa_face_interna"]:
            a, b = deslocar_externa(p, tipo.Width * FT_TO_M)
        linha = DB.Line.CreateBound(_xyz(DB, a, nivel.Elevation), _xyz(DB, b, nivel.Elevation))
        parede = DB.Wall.Create(doc, linha, tipo.Id, nivel.Id, altura, 0.0, False, False)
        if acima is not None:
            restricao = parede.get_Parameter(DB.BuiltInParameter.WALL_HEIGHT_TYPE)
            if restricao is not None and not restricao.IsReadOnly:
                restricao.Set(acima.Id)
        _marcar(DB, parede)
        criadas += 1
    return criadas


def _definir(DB, elemento, parametro, valor):
    p = elemento.get_Parameter(parametro)
    if p is not None and not p.IsReadOnly:
        p.Set(valor)


def _criar_ambientes(doc, DB, salas, nivel):
    criados = 0
    for s in salas:
        if s["sem_parede"]:
            continue
        x, y = ponto_interno(s["lacos"])
        ambiente = doc.Create.NewRoom(nivel, DB.UV(x / FT_TO_M, y / FT_TO_M))
        _definir(DB, ambiente, DB.BuiltInParameter.ROOM_NAME, s["nome"])
        _definir(DB, ambiente, DB.BuiltInParameter.ROOM_DEPARTMENT, s["setor"])
        _marcar(DB, ambiente)
        criados += 1
    return criados


def _criar_pisos(doc, DB, salas, nivel, tipos_piso, cfg):
    from System.Collections.Generic import List

    criados = 0
    for s in salas:
        nome_tipo = cfg["piso_por_setor"].get(s["setor"]) or cfg["piso_oficial"]
        tipo = _escolher(tipos_piso, nome_tipo) if nome_tipo else None
        if tipo is None:
            continue
        lacos = List[DB.CurveLoop]()
        for laco in s["lacos"]:
            loop = DB.CurveLoop()
            pts = [_xyz(DB, p, nivel.Elevation) for p in laco]
            for a, b in zip(pts, pts[1:] + pts[:1]):
                loop.Append(DB.Line.CreateBound(a, b))
            lacos.Add(loop)
        piso = DB.Floor.Create(doc, lacos, tipo.Id, nivel.Id)
        _marcar(DB, piso)
        criados += 1
    return criados


def _salvar_csv(doc, salas):
    pasta = os.path.dirname(doc.PathName or "") or os.path.expanduser("~")
    base = os.path.splitext(os.path.basename(doc.PathName or "modelo"))[0]
    caminho = os.path.join(pasta, "salas_%s.csv" % base)
    with io.open(caminho, "w", encoding="utf-8-sig") as f:  # BOM: Excel abre com acento
        f.write(tabela_csv(salas))
    return caminho


def executar(doc, DB, executar_criacao, config_texto, iniciar=None, concluir=None):
    cfg = ler_config(config_texto)
    linhas = [
        "SALAS → PAREDES — " + ("EXECUÇÃO" if executar_criacao else "SIMULAÇÃO (nada foi alterado)"),
        "",
    ]
    salas, sem_nome, curvas = ler_salas(doc, DB, cfg)
    if not salas:
        linhas.append("Nenhum piso com nome no Comentários%s." % (
            " nos níveis %s" % cfg["niveis"] if cfg["niveis"] else ""))
        return "\n".join(linhas)

    por_nivel = defaultdict(list)
    for s in salas:
        por_nivel[(s["elev"], s["nivel"])].append(s)

    tipos_parede = _tipos(doc, DB, DB.WallType, lambda t: t.Kind == DB.WallKind.Basic)
    tipos_piso = _tipos(doc, DB, DB.FloorType)
    escolha = {
        "interna": _escolher(tipos_parede, cfg["parede_interna"]),
        "externa": _escolher(tipos_parede, cfg["parede_externa"] or cfg["parede_interna"]),
    }

    linhas.append("Salas lidas: %d em %d pavimento(s) · pisos sem nome (ignorados): %d" % (
        len(salas), len(por_nivel), sem_nome))
    if curvas:
        linhas.append("  %d bordas curvas viraram trechos retos (paredes em segmentos)." % curvas)
    linhas.append("")
    linhas.append("Setores (área de piso das salas):")
    total = 0.0
    for setor, n, a in resumo_setores(salas):
        linhas.append("  %-28s %3d salas  %9.2f m²" % (setor, n, a))
        total += a
    linhas.append("  %-28s %3d salas  %9.2f m²" % ("TOTAL", len(salas), total))
    linhas.append("  (setor vem do %s do piso; renomeie com \"mapa_setores\")" % (
        "tipo" if cfg["setor_de"] == "tipo" else "material"))

    planos = {}
    linhas.append("")
    linhas.append("Paredes planejadas (junta até %.2f m · altura %s%s):" % (
        cfg["junta_max_m"],
        "até o nível acima" if cfg["ate_nivel_acima"] else "%.2f m" % cfg["altura_m"],
        " · pedaços da mesma sala sem parede entre si" if cfg["unir_mesmo_nome"] else ""))
    for (elev, nome_nivel), lista in sorted(por_nivel.items()):
        paredes = planejar_paredes(lista, cfg["junta_max_m"], cfg["unir_mesmo_nome"])
        planos[(elev, nome_nivel)] = paredes
        tipos = Counter(p["tipo"] for p in paredes)
        compr = defaultdict(float)
        for p in paredes:
            compr[p["tipo"]] += math.hypot(p["b"][0] - p["a"][0], p["b"][1] - p["a"][1])
        abertas = [s["nome"] for s in lista if s["sem_parede"]]
        linhas.append("  %s: %d salas → %d internas (%.0f m) + %d externas (%.0f m)%s" % (
            nome_nivel, len(lista), tipos["interna"], compr["interna"], tipos["externa"], compr["externa"],
            " · sem parede: %s" % ", ".join(abertas) if abertas else ""))

    linhas.append("")
    for lado in ("interna", "externa"):
        t = escolha[lado]
        linhas.append("Parede %s: %s" % (lado, ("%s (%.0f cm)" % (_nome(DB, t), t.Width * FT_TO_M * 100)) if t else
                                         "NÃO ENCONTRADO: '%s'" % cfg["parede_" + lado]))
    linhas.append("  tipos disponíveis: %s" % ", ".join(sorted(tipos_parede)))
    if cfg["piso_oficial"] or cfg["piso_por_setor"]:
        faltando = [n for n in [cfg["piso_oficial"]] + list(cfg["piso_por_setor"].values()) if n and _escolher(tipos_piso, n) is None]
        linhas.append("Piso oficial: %s%s" % (cfg["piso_oficial"] or "(só por setor)",
                                              " · NÃO ENCONTRADO: %s" % ", ".join(faltando) if faltando else ""))
        linhas.append("  tipos de piso disponíveis: %s" % ", ".join(sorted(tipos_piso)))
    else:
        linhas.append("Piso oficial: não cria (informe \"piso_oficial\" com um dos tipos de piso)")

    avisos = problemas_das_salas(salas)
    if avisos:
        linhas.append("")
        linhas.append("Conferir antes de executar:")
        linhas += ["  " + a for a in avisos[:25]]

    if cfg["salvar_tabela"]:
        try:
            linhas.append("")
            linhas.append("Tabela de salas salva em: %s" % _salvar_csv(doc, salas))
        except Exception as erro:
            linhas.append("Tabela de salas não foi salva: %s" % erro)

    existentes = _marcados(doc, DB)
    linhas.append("Elementos criados antes por este script: %d (serão apagados e recriados)" % len(existentes))

    if not executar_criacao:
        linhas += ["", "Com Executar = True: apaga os %d antigos e cria paredes%s%s." % (
            len(existentes),
            ", ambientes" if cfg["criar_ambientes"] else "",
            " e pisos oficiais" if (cfg["piso_oficial"] or cfg["piso_por_setor"]) else "")]
        return "\n".join(linhas)
    if cfg["criar_paredes"] and (escolha["interna"] is None or escolha["externa"] is None):
        linhas += ["", "Parei: tipo de parede não encontrado (veja os nomes disponíveis acima)."]
        return "\n".join(linhas)

    if iniciar:
        iniciar()  # no Dynamo: fecha a transação dele para usarmos as nossas
    try:
        coletor = _classe_coletor(DB)()
    except Exception:
        coletor = None
    grupo = DB.TransactionGroup(doc, "TCC: salas → paredes")
    grupo.Start()
    resultado = []
    avisos_revit = Counter()
    try:
        ok, apagados, erros = _rodar(doc, DB, "TCC: apagar automáticos", coletor,
                                     lambda: len(list(doc.Delete(_lista_ids(DB, existentes)))) if existentes else 0)
        resultado.append("Apagados (execução anterior): %s" % (apagados if ok else "FALHOU %s" % erros))
        for (elev, nome_nivel), lista in sorted(por_nivel.items()):
            nivel = doc.GetElement(lista[0]["nivel_id"])
            partes = []
            if cfg["criar_paredes"]:
                ok, n, erros = _rodar(doc, DB, "TCC: paredes %s" % nome_nivel, coletor,
                                      lambda: _criar_paredes(doc, DB, planos[(elev, nome_nivel)], nivel, escolha, cfg))
                partes.append("paredes %s" % (n if ok else "DESFEITAS: %s" % "; ".join(erros[:3])))
            if cfg["criar_ambientes"]:
                ok, n, erros = _rodar(doc, DB, "TCC: ambientes %s" % nome_nivel, coletor,
                                      lambda: _criar_ambientes(doc, DB, lista, nivel))
                partes.append("ambientes %s" % (n if ok else "DESFEITOS: %s" % "; ".join(erros[:3])))
            if cfg["piso_oficial"] or cfg["piso_por_setor"]:
                ok, n, erros = _rodar(doc, DB, "TCC: pisos %s" % nome_nivel, coletor,
                                      lambda: _criar_pisos(doc, DB, lista, nivel, tipos_piso, cfg))
                partes.append("pisos %s" % (n if ok else "DESFEITOS: %s" % "; ".join(erros[:3])))
            resultado.append("  %s: %s" % (nome_nivel, " · ".join(partes)))
            avisos_revit.update(_FALHAS["avisos"])
            del _FALHAS["avisos"][:]
    finally:
        grupo.Assimilate()  # um único "Desfazer" (Ctrl+Z) para a execução inteira
        if concluir:
            concluir()
    linhas += [""] + resultado
    if avisos_revit:
        linhas.append("Avisos do Revit (descartados):")
        linhas += ["  %dx %s" % (n, t) for t, n in avisos_revit.most_common(10)]
    linhas += ["", "Ctrl+Z desfaz tudo de uma vez. Confira em 3D e na planta de cada pavimento."]
    return "\n".join(linhas)


def _lista_ids(DB, ids):
    from System.Collections.Generic import List

    lista = List[DB.ElementId]()
    for i in ids:
        lista.Add(i)
    return lista
