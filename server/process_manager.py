"""
Process Manager for Claude CLI subprocess management.
Handles spawning, communication, and lifecycle of Claude agents.
"""

import subprocess
import threading
import queue
import json
import re
import os
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for a Claude agent."""
    agent_id: str
    name: str
    cwd: str
    model: str = "sonnet"
    system_prompt: Optional[str] = None
    session_id: Optional[str] = None


class ProcessManager:
    """Manages Claude CLI subprocesses for agents."""

    def __init__(self):
        self.active_processes: Dict[str, subprocess.Popen] = {}
        self.message_queues: Dict[str, queue.Queue] = {}
        self.locks: Dict[str, threading.Lock] = {}

    def _get_lock(self, agent_id: str) -> threading.Lock:
        """Get or create lock for an agent."""
        if agent_id not in self.locks:
            self.locks[agent_id] = threading.Lock()
        return self.locks[agent_id]

    def send_message(
        self,
        config: AgentConfig,
        message: str,
        on_complete: Optional[Callable[[str, Optional[str]], None]] = None
    ) -> Optional[str]:
        """
        Send a message to a Claude agent and get the response.

        Args:
            config: Agent configuration
            message: Message to send
            on_complete: Callback(response, session_id) when done

        Returns:
            Response text from Claude, or None if error
        """
        lock = self._get_lock(config.agent_id)

        with lock:
            try:
                # Build command
                cmd = ["claude", "--print"]

                # Add model
                if config.model:
                    cmd.extend(["--model", config.model])

                # Add system prompt
                if config.system_prompt:
                    cmd.extend(["--append-system-prompt", config.system_prompt])

                # Resume session if available
                if config.session_id:
                    cmd.extend(["--resume", config.session_id])

                # Add the message
                cmd.append(message)

                logger.info(f"Running command for agent {config.agent_id}: {' '.join(cmd[:5])}...")

                # Run process
                result = subprocess.run(
                    cmd,
                    cwd=config.cwd,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                    env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "agent-chat"}
                )

                if result.returncode != 0:
                    logger.error(f"Claude CLI error: {result.stderr}")
                    response = f"Error: {result.stderr}"
                else:
                    response = result.stdout.strip()

                # Extract session ID from output if present
                session_id = self._extract_session_id(result.stderr)

                if on_complete:
                    on_complete(response, session_id)

                return response

            except subprocess.TimeoutExpired:
                logger.error(f"Timeout for agent {config.agent_id}")
                if on_complete:
                    on_complete("Error: Request timed out after 5 minutes", None)
                return "Error: Request timed out after 5 minutes"

            except Exception as e:
                logger.error(f"Exception for agent {config.agent_id}: {e}")
                if on_complete:
                    on_complete(f"Error: {str(e)}", None)
                return f"Error: {str(e)}"

    def _extract_session_id(self, stderr: str) -> Optional[str]:
        """Extract session ID from Claude CLI output."""
        # Look for session ID pattern in stderr
        # Format: "Session ID: abc12345" or similar
        match = re.search(r'session[_\s]?id[:\s]+([a-f0-9-]+)', stderr, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def is_busy(self, agent_id: str) -> bool:
        """Check if an agent is currently processing."""
        lock = self._get_lock(agent_id)
        return lock.locked()

    def send_message_async(
        self,
        config: AgentConfig,
        message: str,
        on_complete: Callable[[str, Optional[str]], None]
    ) -> threading.Thread:
        """
        Send message asynchronously in a background thread.

        Args:
            config: Agent configuration
            message: Message to send
            on_complete: Callback(response, session_id) when done

        Returns:
            Thread object for the async operation
        """
        thread = threading.Thread(
            target=self.send_message,
            args=(config, message, on_complete),
            daemon=True
        )
        thread.start()
        return thread


# Singleton instance
_process_manager = None


def get_process_manager() -> ProcessManager:
    """Get the singleton ProcessManager instance."""
    global _process_manager
    if _process_manager is None:
        _process_manager = ProcessManager()
    return _process_manager


if __name__ == "__main__":
    # Test the process manager
    pm = get_process_manager()

    config = AgentConfig(
        agent_id="test",
        name="Test Agent",
        cwd=str(Path.home()),
        model="haiku"
    )

    response = pm.send_message(config, "Say hello in exactly 3 words.")
    print(f"Response: {response}")
