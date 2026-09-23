"""Identificacion de tipo de registro (equivalente a DerIdentificarRegistro +
SplitTipoRegistro). Ver docs/matriz_equivalencia.md seccion 2: verificado
empiricamente contra entrada_real_1000.txt, sin export ADF disponible.
"""

from __future__ import annotations

from etl_pmc.config.layouts import Layout
from etl_pmc.models import LineaCruda, TipoRegistro


def identificar_tipo(linea: LineaCruda, layout: Layout) -> TipoRegistro:
    if not linea.contenido:
        return TipoRegistro.INVALIDO

    digito = linea.contenido[0]
    longitud = len(linea.contenido)

    for nombre, spec in layout.record_types.items():
        if digito == spec.type_digit and longitud == spec.length:
            return TipoRegistro(nombre)

    return TipoRegistro.INVALIDO
