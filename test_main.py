"""
Tests para LANOT_ceniza
"""

import unittest
from unittest.mock import patch
import io
import sys

# Importar el módulo principal
import main


class TestMain(unittest.TestCase):
    """Tests para la función main."""

    def test_main_prints_welcome(self):
        """Verifica que main() imprime el mensaje de bienvenida."""
        # Capturar la salida estándar
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        # Ejecutar la función main
        main.main()
        
        # Restaurar la salida estándar
        sys.stdout = sys.__stdout__
        
        # Verificar que se imprimió el mensaje correcto
        output = captured_output.getvalue()
        self.assertIn("LANOT_ceniza", output)
        self.assertIn("Popocatépetl", output)
        self.assertIn("Iniciando aplicación", output)


if __name__ == "__main__":
    unittest.main()
