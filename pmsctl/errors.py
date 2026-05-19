"""Excepciones propias de pmsctl.

Centralizar los errores permite que la interfaz de línea de comandos devuelva
mensajes homogéneos y que cada módulo comunique fallos sin imprimir directamente
por pantalla.
"""


class PmsctlError(Exception):
    """Error funcional controlado por la herramienta.

    ``code`` identifica el tipo de error de forma estable para salidas JSON.
    ``message`` contiene una explicación comprensible para el operador.
    ``recommended_action`` indica una acción de corrección cuando sea posible.
    ``details`` permite añadir datos técnicos sin obligar al usuario a leerlos
    en la salida humana por defecto.
    """

    def __init__(self, code, message, recommended_action=None, details=None):
        Exception.__init__(self, message)
        self.code = code
        self.message = message
        self.recommended_action = recommended_action
        self.details = details or {}

    def to_dict(self):
        """Devuelve el error en una forma serializable como JSON."""

        data = {
            "result": "ERROR",
            "error_code": self.code,
            "message": self.message,
        }
        if self.recommended_action:
            data["recommended_action"] = self.recommended_action
        if self.details:
            data["details"] = self.details
        return data
