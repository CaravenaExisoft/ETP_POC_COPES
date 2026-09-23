"""Layouts declarativos de ancho fijo.

Las posiciones se documentan siempre 1-based (como en docs/matriz_equivalencia.md
y en el prompt). La conversion a slices Python (0-based, fin exclusivo) sucede
en un unico lugar de este modulo: FieldSpec.slice(). Ningun otro modulo debe
hacer aritmetica de posiciones por su cuenta.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Literal

from etl_pmc.errors import LayoutError

FieldKind = Literal["text", "text_trim", "date_yyyymmdd", "amount_comma2", "integer"]


@dataclass(frozen=True)
class FieldSpec:
    name: str
    start: int  # 1-based, inclusivo
    length: int
    kind: FieldKind
    estado: str  # CONFIRMADA_ADF | PROPUESTA_GUIA | SUPUESTO_POC | POSTERGADA

    def __post_init__(self) -> None:
        if self.start < 1:
            raise LayoutError(f"Campo '{self.name}': 'start' debe ser 1-based (>=1), recibido {self.start}")
        if self.length < 1:
            raise LayoutError(f"Campo '{self.name}': 'length' debe ser >=1, recibido {self.length}")

    @property
    def end(self) -> int:
        """Posicion final, 1-based, inclusiva."""
        return self.start + self.length - 1

    def slice(self) -> slice:
        """Unico punto de conversion 1-based -> slice Python 0-based."""
        return slice(self.start - 1, self.start - 1 + self.length)

    def extract_raw(self, line: str) -> str:
        """Extrae el campo sin aplicar strip salvo que el kind sea text_trim.

        No se debe aplicar strip() generico al registro completo (el ancho fijo
        incluye espacios finales con significado); el trim, si corresponde, es
        una decision explicita por campo, documentada en el layout.
        """
        raw = line[self.slice()]
        if self.kind == "text_trim":
            return raw.strip()
        return raw


@dataclass(frozen=True)
class RecordTypeSpec:
    type_digit: str
    length: int


@dataclass(frozen=True)
class Layout:
    profile: str
    layout_version: int
    source: str
    record_types: dict[str, RecordTypeSpec]
    cabecera_fields: tuple[FieldSpec, ...]
    detalle_fields: tuple[FieldSpec, ...]
    pie_fields: tuple[FieldSpec, ...]

    def detalle_field(self, name: str) -> FieldSpec:
        for f in self.detalle_fields:
            if f.name == name:
                return f
        raise LayoutError(f"Perfil '{self.profile}': el campo de detalle '{name}' no esta definido en el layout")

    def cabecera_field(self, name: str) -> FieldSpec:
        for f in self.cabecera_fields:
            if f.name == name:
                return f
        raise LayoutError(f"Perfil '{self.profile}': el campo de cabecera '{name}' no esta definido en el layout")

    def pie_field(self, name: str) -> FieldSpec:
        for f in self.pie_fields:
            if f.name == name:
                return f
        raise LayoutError(f"Perfil '{self.profile}': el campo de pie '{name}' no esta definido en el layout")

    def validate_against_record_length(self) -> None:
        """Ningun campo puede exceder la longitud declarada de su tipo de registro."""
        checks = (
            ("cabecera", self.cabecera_fields),
            ("detalle", self.detalle_fields),
            ("pie", self.pie_fields),
        )
        for type_name, fields in checks:
            record_type = self.record_types.get(type_name)
            if record_type is None:
                raise LayoutError(f"Perfil '{self.profile}': falta record_types['{type_name}']")
            for f in fields:
                if f.end > record_type.length:
                    raise LayoutError(
                        f"Perfil '{self.profile}': el campo '{f.name}' termina en la posicion {f.end}, "
                        f"que excede la longitud declarada de '{type_name}' ({record_type.length})"
                    )


_PROFILE_FILES = {
    "poc_pmc": "poc_pmc_v1.json",
}

# adf_actual queda deliberadamente sin archivo: no hay export ADF confiable
# todavia (ver docs/matriz_equivalencia.md seccion 0). Seleccionarlo debe
# fallar con un error de configuracion explicito, nunca caer en poc_pmc.


def _field_from_dict(d: dict) -> FieldSpec:
    return FieldSpec(
        name=d["name"],
        start=d["start"],
        length=d["length"],
        kind=d["kind"],
        estado=d["estado"],
    )


def load_layout(profile: str) -> Layout:
    if profile not in _PROFILE_FILES:
        known = ", ".join(sorted(_PROFILE_FILES))
        raise LayoutError(
            f"Perfil '{profile}' no tiene layout disponible. "
            f"Perfiles con layout cargable actualmente: {known}. "
            "'adf_actual' no esta poblado porque no existe un export ADF confiable "
            "(ver docs/matriz_equivalencia.md seccion 0/11)."
        )
    filename = _PROFILE_FILES[profile]
    raw = resources.files("etl_pmc.config.layout_data").joinpath(filename).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LayoutError(f"Layout '{filename}' no es JSON valido: {exc}") from exc

    record_types = {
        name: RecordTypeSpec(type_digit=rt["type_digit"], length=rt["length"])
        for name, rt in data["record_types"].items()
    }
    layout = Layout(
        profile=data["profile"],
        layout_version=data["layout_version"],
        source=data["source"],
        record_types=record_types,
        cabecera_fields=tuple(_field_from_dict(f) for f in data["cabecera_fields"]),
        detalle_fields=tuple(_field_from_dict(f) for f in data["detalle_fields"]),
        pie_fields=tuple(_field_from_dict(f) for f in data["pie_fields"]),
    )
    layout.validate_against_record_length()
    return layout
