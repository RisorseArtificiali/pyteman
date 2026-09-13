# tests/test_sitecustomize.py
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
SRC = HERE.parent / "src" / "pyteman"  # dir on PYTHONPATH makes sitecustomize top-level importable

TARGET = "def plain(a, b=0):\n    return a + b\n"
RULES = """
- id: ov
  point: target_mod.plain
  event: entry
  action: {kind: return_value, value: 42}
"""

def run_py(tmp, env_extra, code):
    env = {**os.environ, "PYTHONPATH": f"{tmp}:{SRC}", **env_extra}
    return subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, env=env, cwd=str(tmp))

def test_inert_without_env(tmp_path):
    (tmp_path / "target_mod.py").write_text(TARGET)
    r = run_py(tmp_path, {},
               "import target_mod, sys; print(target_mod.plain(1)); "
               "print('hooked' if getattr(sys, '_pyteman', None) else 'clean')")
    assert r.stdout.splitlines() == ["1", "clean"]

def test_active_with_rules(tmp_path):
    (tmp_path / "target_mod.py").write_text(TARGET)
    (tmp_path / "r.yaml").write_text(RULES)
    r = run_py(tmp_path, {"PYTEMAN_RULES": str(tmp_path / "r.yaml")},
               "import target_mod; print(target_mod.plain(1)); "
               "print(open('pyteman.log').read().count(chr(10)))")
    assert r.stdout.splitlines()[0] == "42"
    assert int(r.stdout.splitlines()[1]) >= 1

def test_marker_refusal(tmp_path):
    (tmp_path / "target_mod.py").write_text(TARGET)
    (tmp_path / "r.yaml").write_text(RULES)
    r = run_py(tmp_path, {"PYTEMAN_RULES": str(tmp_path / "r.yaml"),
                          "PYTEMAN_REQUIRE_MARKER": str(tmp_path / "nope" / "MARK.ok")},
               "import target_mod; print(target_mod.plain(1))")
    assert r.returncode == 2
    assert "marker" in r.stderr.lower()
