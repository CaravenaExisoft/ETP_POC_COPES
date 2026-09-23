"""Excepciones propias del motor. Un error de configuracion nunca debe
confundirse con un rechazo de datos de negocio: el primero impide arrancar
la corrida, el segundo es un resultado esperado del procesamiento."""


class ConfigurationError(Exception):
    """Falta o es invalida una configuracion requerida (layout, manifiesto,
    parametros). El prompt exige un error claro en vez de adivinar un valor."""


class LayoutError(ConfigurationError):
    """El layout declarativo es invalido o incompleto para el perfil pedido."""


class EnrichmentError(Exception):
    """Problema con los datos de enriquecimiento (CSV faltante/vacio/columna
    ausente/nulo/multiples filas). Es un rechazo de datos de la corrida, no un
    error de configuracion: el manifiesto estaba bien formado, el contenido
    del CSV de la corrida no permite continuar. Prompt seccion 8: cada caso se
    distingue explicitamente, ninguno cae en un fallback silencioso."""

    def __init__(self, codigo: str, mensaje: str) -> None:
        super().__init__(f"{codigo}: {mensaje}")
        self.codigo = codigo
