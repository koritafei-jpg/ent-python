from entpy.dialect.sqlalchemy.pgvector import VectorType


def test_vector_type_sqlite_bind():
    vt = VectorType(8)
    val = vt.process_bind_param([1.0, 2.0], type("D", (), {"name": "sqlite"})())
    assert isinstance(val, str)
