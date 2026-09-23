"""Validacion de schema XSD SINTETICA -- INVENTADA a pedido explicito del
usuario, NO es el XSD productivo real (prompt seccion 17: "XSD productivo no
entregado"; GDC-1000 seccion B menciona "Control de formatos (XSD)" como una
de las cinco validaciones que existen en produccion, sin adjuntar el schema).

Objetivo unico: tener un paso de "parsear el registro a un arbol XML y
validarlo contra un schema" con un costo por registro comparable al que
probablemente paga IIB, para poder MEDIR cuanto pesa ese tipo de paso a
escala real (~630.000 registros) y asi evaluar si explica parte de la
diferencia de tiempo frente al proceso legado (docs/supuestos_y_pendientes.md).

No se debe usar como evidencia de conformidad con ningun XSD productivo, y no
reemplaza ninguna de las validaciones ya implementadas en
etl_pmc.validation.detalle -- es deliberadamente redundante con ellas.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

from lxml import etree

from etl_pmc.models import DetalleCrudo


class SchemaSinteticoError(Exception):
    """El registro no matchea el schema XSD sintetico (inventado)."""


@lru_cache(maxsize=1)
def _cargar_schema() -> etree.XMLSchema:
    contenido = (
        resources.files("etl_pmc.config.schema_sintetico")
        .joinpath("registro_sap_sintetico.xsd")
        .read_bytes()
    )
    return etree.XMLSchema(etree.fromstring(contenido))


def _hijo(padre: "etree._Element", tag: str, valor: str) -> None:
    el = etree.SubElement(padre, tag)
    el.text = valor


def validar_detalle_schema(crudo: DetalleCrudo) -> None:
    """Construye el arbol XML del registro (como haria un mensaje IIB) y lo
    valida contra el schema sintetico. Lanza SchemaSinteticoError si no
    matchea; no devuelve nada si es valido."""
    root = etree.Element("Detalle")
    _hijo(root, "ReferenciaCliente", crudo.referencia_cliente_raw)
    _hijo(root, "IdDeuda", crudo.id_deuda_raw)
    _hijo(root, "PrimerVencimiento", crudo.primer_vencimiento_raw)
    _hijo(root, "Moneda", crudo.moneda_raw)
    _hijo(root, "ImportePrincipal", crudo.importe_principal_raw)
    _hijo(root, "NombreEntidad", crudo.nombre_entidad_raw)
    _hijo(root, "Concepto", crudo.concepto_raw)
    _hijo(root, "SegundoVencimiento", crudo.segundo_vencimiento_raw)
    _hijo(root, "ImporteSegundoVencimiento", crudo.importe_segundo_vencimiento_raw)
    _hijo(root, "TercerVencimiento", crudo.tercer_vencimiento_raw)
    _hijo(root, "ImporteTercerVencimiento", crudo.importe_tercer_vencimiento_raw)

    schema = _cargar_schema()
    if not schema.validate(root):
        error = schema.error_log.last_error
        raise SchemaSinteticoError(str(error) if error is not None else "el registro no matchea el schema sintetico")
