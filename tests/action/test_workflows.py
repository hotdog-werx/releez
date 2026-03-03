"""Auto-discover and run GitHub Action test workflows via act.

Each ``test-action-*.yaml`` file in this directory becomes a pytest test.
By default the workflow is dispatched with a ``workflow_dispatch`` event.

If a matching ``<stem>.input.json`` file exists it controls the invocation:

.. code-block:: json

    {
        "event_type": "pull_request",
        "payload": { ... }
    }

``event_type`` overrides the default ``workflow_dispatch`` trigger and
``payload`` is written to a temp file and passed to act via ``-e``.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_TESTS_DIR = Path(__file__).resolve().parent

_workflow_files = sorted(_TESTS_DIR.glob('test-action-*.yaml'))


def _build_cmd(
    workflow: Path,
    input_data: dict | None,
) -> tuple[list[str], Path | None]:
    rel = str(workflow.relative_to(_REPO_ROOT))
    if input_data is None:
        return [
            'mise',
            'exec',
            '--',
            'act',
            'workflow_dispatch',
            '-W',
            rel,
        ], None

    event_type = input_data['event_type']
    payload = input_data.get('payload', {})

    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.json',
        delete=False,
    ) as tmp:
        json.dump(payload, tmp)
        tmp.close()
        payload_path = Path(tmp.name)

        return [
            'mise',
            'exec',
            '--',
            'act',
            event_type,
            '-W',
            rel,
            '-e',
            str(payload_path),
        ], payload_path


@pytest.mark.action
@pytest.mark.parametrize('workflow', _workflow_files, ids=lambda p: p.stem)
def test_action_workflow(workflow: Path) -> None:
    input_file = workflow.with_name(workflow.stem + '.input.json')
    input_data = json.loads(input_file.read_text()) if input_file.exists() else None

    cmd, payload_path = _build_cmd(workflow, input_data)
    try:
        result = subprocess.run(cmd, check=False, cwd=_REPO_ROOT)  # noqa: S603
    finally:
        if payload_path is not None:
            payload_path.unlink(missing_ok=True)

    assert result.returncode == 0, f'act exited with code {result.returncode}'
