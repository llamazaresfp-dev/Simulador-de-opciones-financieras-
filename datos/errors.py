"""Errores del paquete datos/ y sus mensajes en español para el usuario.

Cada error trae un mensaje listo para mostrar en la app (st.error o
st.warning), nunca un traceback.
"""

MSG_NETWORK = (
    "No se pudo conectar con el proveedor de datos. "
    "Revisa tu conexión a internet e inténtalo de nuevo."
)
MSG_RATE_LIMIT = (
    "El proveedor de datos ha limitado las solicitudes por ahora. "
    "Espera unos minutos antes de volver a cargar."
)
MSG_EMPTY = "El proveedor de datos devolvió una respuesta vacía para este subyacente."
MSG_NO_LIQUID = (
    "Ahora mismo no hay opciones líquidas para este subyacente "
    "(puede que el mercado esté cerrado o sea fin de semana)."
)


class DatosError(Exception):
    """Error base de los datos de mercado; guarda el mensaje en español."""

    default_message = MSG_NETWORK

    def __init__(self, message: str | None = None):
        # Si no se pasa un mensaje, se usa el de la clase.
        if message is None:
            message = self.default_message
        self.message = message
        super().__init__(message)


class NetworkError(DatosError):
    """Fallo de red: sin conexión, timeout o error de conexión."""

    default_message = MSG_NETWORK


class RateLimitError(DatosError):
    """El proveedor limitó las solicitudes (HTTP 429)."""

    default_message = MSG_RATE_LIMIT


class EmptyDataError(DatosError):
    """El proveedor respondió, pero sin datos útiles."""

    default_message = MSG_EMPTY
