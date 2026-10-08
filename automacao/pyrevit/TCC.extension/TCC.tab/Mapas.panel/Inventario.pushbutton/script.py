# -*- coding: utf-8 -*-
"""Botão pyRevit: inventário somente leitura do modelo aberto."""

import os
import sys

from Autodesk.Revit import DB

_SCRIPTS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "scripts")
)
if _SCRIPTS not in sys.path:
    sys.path.append(_SCRIPTS)

import tcc_inventario  # noqa: E402

doc = __revit__.ActiveUIDocument.Document  # noqa: F821 — injetado pelo pyRevit
print(tcc_inventario.executar(doc, __revit__.Application.VersionName, DB))  # noqa: F821
