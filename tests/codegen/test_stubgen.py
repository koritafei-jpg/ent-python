"""类型桩与薄封装代码生成。"""

from pathlib import Path

from entpy.codegen.stubgen import generate_stubs
from entpy.codegen.thin import generate_thin_wrappers
from examples.start.models import SCHEMAS


def test_generate_stubs(tmp_path: Path):
    paths = generate_stubs(SCHEMAS, tmp_path / "stubs")
    assert any(p.suffix == ".pyi" for p in paths)
    user_stub = tmp_path / "stubs" / "user_predicates.pyi"
    assert user_stub.exists()
    content = user_stub.read_text()
    assert "name: FieldRef" in content
    assert "age: FieldRef" in content


def test_generate_thin_wrappers(tmp_path: Path):
    paths = generate_thin_wrappers(SCHEMAS, tmp_path / "gen", package="ent_generated")
    client_py = tmp_path / "gen" / "client.py"
    assert client_py.exists()
    assert "create_user" in client_py.read_text()
