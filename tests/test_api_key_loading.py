"""Verify key resolution without importing the Streamlit application UI."""
import ast
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


APP = Path(__file__).resolve().parents[1] / 'app.py'
module = ast.parse(APP.read_text(encoding='utf-8'))
func = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == 'streamlit_key')
namespace = {'os': os, 'st': SimpleNamespace(secrets={})}
exec(compile(ast.Module(body=[func], type_ignores=[]), str(APP), 'exec'), namespace)


class KeyLoadingTests(unittest.TestCase):
    def test_secret_preferred_over_environment(self):
        namespace['st'].secrets = {'OPENAI_API_KEY': 'secret-key'}
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'environment-key'}):
            self.assertEqual(namespace['streamlit_key'](), 'secret-key')

    def test_environment_fallback(self):
        namespace['st'].secrets = {}
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'environment-key'}):
            self.assertEqual(namespace['streamlit_key'](), 'environment-key')

    def test_missing_key_returns_empty(self):
        namespace['st'].secrets = {}
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(namespace['streamlit_key'](), '')


if __name__ == '__main__':
    unittest.main()
