"""
PTY Manager for Agent Chat.
Manages pseudo-terminals running Claude CLI for each agent.
"""

import os
import pty
import subprocess
import select
import signal
import struct
import fcntl
import termios
from typing import Dict, Optional, Callable
from dataclasses import dataclass, field
from threading import Thread, Lock
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PTYSession:
    """Represents an active PTY session."""
    agent_id: str
    pid: int
    fd: int
    cwd: str
    model: str
    output_callback: Optional[Callable[[bytes], None]] = None
    scrollback: bytes = field(default_factory=bytes)
    max_scrollback: int = 50000  # ~50KB of scrollback
    rows: int = 24
    cols: int = 80


class PTYManager:
    """Manages PTY sessions for agents."""

    def __init__(self):
        self.sessions: Dict[str, PTYSession] = {}
        self.lock = Lock()
        self._reader_threads: Dict[str, Thread] = {}

    def create_session(
        self,
        agent_id: str,
        cwd: str,
        model: str = "sonnet",
        system_prompt: Optional[str] = None,
        output_callback: Optional[Callable[[bytes], None]] = None,
        initial_rows: int = 24,
        initial_cols: int = 80,
        agent_name: Optional[str] = None
    ) -> PTYSession:
        """Create a new PTY session running Claude CLI."""

        with self.lock:
            # Kill existing session if any
            if agent_id in self.sessions:
                self.kill_session(agent_id)

            # Build the claude command
            cmd = ["claude"]
            if model:
                cmd.extend(["--model", model])
            if system_prompt:
                cmd.extend(["--append-system-prompt", system_prompt])

            # Create PTY
            pid, fd = pty.fork()

            if pid == 0:
                # Child process
                os.chdir(cwd)
                os.environ["TERM"] = "xterm-256color"
                os.environ["CLAUDE_CODE_ENTRYPOINT"] = "agent-chat"
                # Set agent identification for hooks
                os.environ["AGENT_CHAT_ID"] = agent_id
                os.environ["AGENT_CHAT_NAME"] = agent_name or agent_id
                os.execvp(cmd[0], cmd)
            else:
                # Parent process
                # Set initial terminal size
                try:
                    winsize = struct.pack("HHHH", initial_rows, initial_cols, 0, 0)
                    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
                    logger.info(f"PTY created with size {initial_cols}x{initial_rows}")
                except OSError:
                    pass

                # Set non-blocking
                flags = fcntl.fcntl(fd, fcntl.F_GETFL)
                fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

                session = PTYSession(
                    agent_id=agent_id,
                    pid=pid,
                    fd=fd,
                    cwd=cwd,
                    model=model,
                    output_callback=output_callback,
                    rows=initial_rows,
                    cols=initial_cols
                )
                self.sessions[agent_id] = session

                # Start reader thread
                reader = Thread(target=self._read_loop, args=(agent_id,), daemon=True)
                self._reader_threads[agent_id] = reader
                reader.start()

                logger.info(f"Created PTY session for agent {agent_id}, pid={pid}")
                return session

    def _read_loop(self, agent_id: str):
        """Background thread that reads PTY output."""
        while True:
            with self.lock:
                session = self.sessions.get(agent_id)
                if not session:
                    break
                fd = session.fd

            try:
                # Use select to wait for data
                r, _, _ = select.select([fd], [], [], 0.1)
                if fd in r:
                    try:
                        data = os.read(fd, 4096)
                        if data:
                            with self.lock:
                                session = self.sessions.get(agent_id)
                                if session:
                                    # Add to scrollback
                                    session.scrollback += data
                                    # Trim if too large
                                    if len(session.scrollback) > session.max_scrollback:
                                        session.scrollback = session.scrollback[-session.max_scrollback:]
                                    # Call callback
                                    if session.output_callback:
                                        try:
                                            session.output_callback(data)
                                        except Exception as e:
                                            logger.error(f"Output callback error: {e}")
                        else:
                            # EOF - process exited
                            logger.info(f"PTY EOF for agent {agent_id}")
                            break
                    except OSError:
                        break
            except (ValueError, OSError):
                # fd closed
                break

    def write(self, agent_id: str, data: bytes) -> bool:
        """Write data to a PTY session."""
        with self.lock:
            session = self.sessions.get(agent_id)
            if not session:
                return False
            try:
                os.write(session.fd, data)
                return True
            except OSError as e:
                logger.error(f"Write error for agent {agent_id}: {e}")
                return False

    def resize(self, agent_id: str, rows: int, cols: int) -> bool:
        """Resize a PTY session."""
        with self.lock:
            session = self.sessions.get(agent_id)
            if not session:
                return False
            try:
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(session.fd, termios.TIOCSWINSZ, winsize)
                session.rows = rows
                session.cols = cols
                return True
            except OSError as e:
                logger.error(f"Resize error for agent {agent_id}: {e}")
                return False

    def get_scrollback(self, agent_id: str) -> bytes:
        """Get scrollback buffer for a session."""
        with self.lock:
            session = self.sessions.get(agent_id)
            if session:
                return session.scrollback
            return b""

    def get_scrollback_info(self, agent_id: str) -> tuple[bytes, int, int]:
        """Get scrollback buffer plus the terminal size it was captured with."""
        with self.lock:
            session = self.sessions.get(agent_id)
            if session:
                return session.scrollback, session.rows, session.cols
            return b"", 24, 80

    def set_output_callback(self, agent_id: str, callback: Optional[Callable[[bytes], None]]):
        """Set the output callback for a session."""
        with self.lock:
            session = self.sessions.get(agent_id)
            if session:
                session.output_callback = callback

    def kill_session(self, agent_id: str) -> bool:
        """Kill a PTY session."""
        with self.lock:
            session = self.sessions.get(agent_id)
            if not session:
                return False

            try:
                os.close(session.fd)
            except OSError:
                pass

            try:
                os.kill(session.pid, signal.SIGTERM)
            except OSError:
                pass

            del self.sessions[agent_id]
            logger.info(f"Killed PTY session for agent {agent_id}")
            return True

    def has_session(self, agent_id: str) -> bool:
        """Check if agent has an active session."""
        with self.lock:
            return agent_id in self.sessions

    def is_alive(self, agent_id: str) -> bool:
        """Check if the PTY process is still alive."""
        with self.lock:
            session = self.sessions.get(agent_id)
            if not session:
                return False
            try:
                pid, status = os.waitpid(session.pid, os.WNOHANG)
                return pid == 0  # 0 means still running
            except ChildProcessError:
                return False

    def list_sessions(self) -> list:
        """List all active session agent IDs."""
        with self.lock:
            return list(self.sessions.keys())


# Singleton
_pty_manager = None


def get_pty_manager() -> PTYManager:
    """Get the singleton PTYManager instance."""
    global _pty_manager
    if _pty_manager is None:
        _pty_manager = PTYManager()
    return _pty_manager
