"""Tests for ops.management.supervisor — _spawn, _stop, _supervise."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from ops.management.supervisor import _spawn, _stop, _supervise


class TestSpawn:
    """Tests for _spawn()."""

    def test_spawn_creates_popen(self) -> None:
        proc = _spawn("echo", "hello")
        assert isinstance(proc, subprocess.Popen)
        proc.wait(timeout=5)
        assert proc.returncode == 0

    def test_spawn_passes_correct_args(self) -> None:
        with patch("subprocess.Popen") as mock_popen:
            _spawn("python3", "manage.py", "test")
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        assert args[0] == ["python3", "manage.py", "test"]

    def test_spawn_passes_base_dir_cwd(self) -> None:
        with patch("subprocess.Popen") as mock_popen:
            _spawn("ls")
        _, kwargs = mock_popen.call_args
        assert kwargs["cwd"] is not None

    def test_spawn_raises_on_popen_failure(self) -> None:
        """_spawn propagates Popen errors (e.g. executable not found)."""
        with patch("subprocess.Popen", side_effect=RuntimeError("exec not found")):
            with pytest.raises(RuntimeError, match="exec not found"):
                _spawn("nonexistent")


class TestStop:
    """Tests for _stop()."""

    def test_stop_terminates_and_waits(self) -> None:
        """_stop calls terminate then wait with timeout."""
        mock_proc = MagicMock()
        with (
            patch("ops.management.supervisor.settings.GRACEFUL_TIMEOUT", 5),
            patch("ops.management.supervisor.time.monotonic", return_value=100),
        ):
            _stop([mock_proc])

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=5)

    def test_stop_kills_on_timeout(self) -> None:
        """When wait times out, _stop calls kill()."""
        mock_proc = MagicMock()
        mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=0.1)
        with patch("ops.management.supervisor.settings.GRACEFUL_TIMEOUT", 0.1):
            _stop([mock_proc])

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once()
        mock_proc.kill.assert_called_once()

    def test_stop_raises_on_unexpected_error(self) -> None:
        """When wait raises a non-TimeoutExpired error, _stop propagates it."""
        mock_proc = MagicMock()
        mock_proc.wait.side_effect = RuntimeError("process died")
        with patch("ops.management.supervisor.settings.GRACEFUL_TIMEOUT", 0.1):
            with pytest.raises(RuntimeError, match="process died"):
                _stop([mock_proc])

        mock_proc.terminate.assert_called_once()

    def test_stop_empty_list(self) -> None:
        """_stop with empty process list should not crash."""
        _stop([])


class TestSupervise:
    """Tests for _supervise()."""

    def test_supervise_exits_when_child_exits(self) -> None:
        """When a child exits with code 0, supervise exits 0."""
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 0]
        mock_proc.returncode = 0

        with (
            patch("ops.management.supervisor.signal.signal"),
            patch(
                "ops.management.supervisor.sys.exit", side_effect=SystemExit
            ) as mock_exit,
            patch("ops.management.supervisor.time.sleep"),
        ):
            with pytest.raises(SystemExit):
                _supervise([mock_proc])

        mock_exit.assert_called_once_with(0)

    def test_supervise_exits_with_child_returncode(self) -> None:
        """When a child fails (non-zero), supervise exits with that code."""
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 1]
        mock_proc.returncode = 1

        with (
            patch("ops.management.supervisor.signal.signal"),
            patch(
                "ops.management.supervisor.sys.exit", side_effect=SystemExit
            ) as mock_exit,
            patch("ops.management.supervisor.time.sleep"),
        ):
            with pytest.raises(SystemExit):
                _supervise([mock_proc])

        mock_exit.assert_called_once_with(1)
