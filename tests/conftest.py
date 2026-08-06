"""Test infrastructure: project-local temp dirs that tolerate restricted sandboxes.

The restricted filesystem profile blocks tempfile.mkdtemp's 0o700 mode and
os.chmod, so stdlib TemporaryDirectory fails to create/write/clean up. This
conftest replaces it with a drop-in that uses os.makedirs (default perms) in a
project-local dir and cleans up with shutil.rmtree(ignore_errors=True).
Harmless in normal environments.
"""

import os
import shutil
import tempfile as _tempfile

_PROJECT_TMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".tmp_tests")
os.makedirs(_PROJECT_TMP, exist_ok=True)
_counter = [0]


class _TemporaryDirectory:
    """Drop-in replacement for tempfile.TemporaryDirectory."""

    def __init__(self, *args, **kwargs):
        _counter[0] += 1
        self.name = os.path.join(_PROJECT_TMP, f"td_{os.getpid()}_{_counter[0]}")
        os.makedirs(self.name, exist_ok=True)

    def __enter__(self):
        return self.name

    def __exit__(self, *exc):
        self.cleanup()
        return False

    def cleanup(self):
        shutil.rmtree(self.name, ignore_errors=True)


_tempfile.TemporaryDirectory = _TemporaryDirectory
