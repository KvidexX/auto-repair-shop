"""Контракты архитектуры, документации и изоляции тестовых артефактов."""
import ast
import re
import subprocess
import unittest

from tests.support import ROOT, SCREENSHOTS


class ArchitectureTests(unittest.TestCase):
    def test_entrypoint_is_small_and_package_does_not_import_it(self):
        self.assertLess(len((ROOT / 'main.py').read_text(encoding='utf-8-sig').splitlines()), 150)
        for path in (ROOT / 'autoservice').glob('*.py'):
            with self.subTest(path=path.name):
                tree = ast.parse(path.read_text(encoding='utf-8'))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        self.assertNotEqual(node.module, 'main')
                        if node.module and node.module.startswith('autoservice'):
                            self.fail(f'Внутренний абсолютный импорт: {path}: {node.module}')
        domain = (ROOT / 'autoservice/data.py').read_text(encoding='utf-8')
        self.assertNotIn('PySide6', domain)
        self.assertNotIn('demo_data', domain)
        self.assertNotIn('CLIENTS =', domain)

    def test_pyinstaller_entrypoint_reaches_all_package_modules_statically(self):
        paths = {'main': ROOT / 'main.py', **{f'autoservice.{p.stem}': p for p in (ROOT / 'autoservice').glob('*.py') if p.stem != '__init__'}}
        graph = {}
        for name, path in paths.items():
            dependencies = set()
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.ImportFrom) and node.module:
                    target = 'autoservice.' + node.module if node.level else node.module
                    if target in paths:
                        dependencies.add(target)
            graph[name] = dependencies
        seen, pending = set(), ['main']
        while pending:
            name = pending.pop()
            if name not in seen:
                seen.add(name)
                pending.extend(graph[name])
        self.assertEqual(seen, set(paths))
        spec = ast.parse((ROOT / 'AutoService.spec').read_text(encoding='utf-8'))
        self.assertTrue(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'Analysis' for n in ast.walk(spec)))

    def test_readme_local_links_and_documentation_images_exist(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8-sig')
        self.assertLess(len(readme.encode('utf-8')), 16000)
        for target in re.findall(r'\]\(([^)]+)\)', readme):
            if not target.startswith(('https://', '#')):
                self.assertTrue((ROOT / target).is_file(), target)

    def test_test_artifacts_are_ignored_and_documentation_pngs_are_unmodified(self):
        self.assertEqual(SCREENSHOTS, ROOT / '.tmp' / 'test-screenshots')
        ignored = subprocess.run(['git', 'check-ignore', str(SCREENSHOTS / 'probe.png')], cwd=ROOT, capture_output=True)
        self.assertEqual(ignored.returncode, 0, ignored.stderr)
        changed = subprocess.run(['git', 'diff', '--name-only', '--', 'screenshots/*.png'], cwd=ROOT, capture_output=True)
        self.assertEqual(changed.returncode, 0)
        self.assertEqual(changed.stdout.strip(), b'')


if __name__ == '__main__':
    unittest.main()
