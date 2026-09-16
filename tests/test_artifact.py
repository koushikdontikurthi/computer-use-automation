from pathlib import Path

from app.replay.executor import load_artifact


def test_example_artifact_is_typed_and_versioned():
    artifact = load_artifact(Path("evidence/example_capability.json"))
    assert artifact.schema_version == "1.0"
    assert artifact.artifact_version == 1
    assert artifact.inputs[0].name == "member_id"
    assert artifact.outputs[0].name == "savings_balance"
    assert len(artifact.steps) == 3
