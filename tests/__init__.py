"""Paquete de tests de Excel Cleaner.

Permite `python -m unittest discover` desde la raíz del proyecto. Las suites
de patrón función (test_cleaner, test_batch, etc.) se ejecutan directamente
con `python tests/<suite>.py`; discovery las importa sin efectos (su main()
está protegido por `if __name__ == "__main__"`).
"""
