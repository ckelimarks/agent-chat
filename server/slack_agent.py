"""
Slack Agent Integration for Agent Chat.

Polls Slack for @mentions, injects them into a designated agent's PTY,
captures the response, and posts back to Slack.

Uses curl (no SDK) and careful state management to prevent duplicates.
"""

import asyncio
import json
import subprocess
import os
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
STATE_FILE = DATA_DIR / "slack_agent_state.json"

# Config
POLL_INTERVAL = 60  # seconds
RESPONSE_TIMEOUT = 120  # max seconds to wait for agent response
IDLE_THRESHOLD = 5  # seconds of no output = response complete


class SlackAgentState(Enum):
    IDLE = "idle"
    PROCESSING = "processing"
    WAITING_RESPONSE = "waiting_response"
    POSTING = "posting"


@dataclass
class SlackAgentConfig:
    """Persistent state for Slack agent integration."""
    state: str = "idle"
    agent_id: Optional[str] = None  # Which agent handles Slack
    channel_id: str = ""
    thread_ts: str = ""
    last_processed_ts: str = ""  # Last message we responded to
    current_message_ts: str = ""  # Message we're currently processing
    last_poll_time: float = 0
    response_buffer: str = ""  # Captured agent output

    @classmethod
    def load(cls) -> "SlackAgentConfig":
        """Load state from file."""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE) as f:
                    data = json.load(f)
                    return cls(**data)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to load state, starting fresh: {e}")
        return cls()

    def save(self):
        """Save state to file."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            json.dump(asdict(self), f, indent=2)
        logger.debug(f"State saved: {self.state}")


def slack_curl(method: str, endpoint: str, data: Optional[Dict] = None) -> Optional[Dict]:
    """Make a Slack API call via curl."""
    token = os.getenv('SLACK_BOT_TOKEN')
    if not token:
        logger.warning("SLACK_BOT_TOKEN not set")
        return None

    url = f"https://slack.com/api/{endpoint}"

    cmd = ['curl', '-s']
    cmd.extend(['-H', f'Authorization: Bearer {token}'])

    if method == 'GET':
        # Add query params to URL
        if data:
            params = '&'.join(f"{k}={v}" for k, v in data.items())
            url = f"{url}?{params}"
    elif method == 'POST':
        cmd.extend(['-H', 'Content-Type: application/json'])
        if data:
            cmd.extend(['-d', json.dumps(data)])

    cmd.append(url)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            response = json.loads(result.stdout)
            if not response.get('ok'):
                logger.error(f"Slack API error: {response.get('error')}")
            return response
        else:
            logger.error(f"curl failed: {result.stderr}")
            return None
    except subprocess.TimeoutExpired:
        logger.error("Slack API timeout")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON from Slack: {e}")
        return None


def get_new_mentions(config: SlackAgentConfig) -> Optional[Dict]:
    """Check for new @mentions in channel or thread since last_processed_ts."""
    if not config.channel_id:
        logger.debug("No channel configured")
        return None

    # If thread_ts is empty or "channel", monitor the whole channel
    monitor_channel = not config.thread_ts or config.thread_ts == "channel"

    if monitor_channel:
        # Use conversations.history for channel-level monitoring
        params = {
            'channel': config.channel_id,
            'limit': '20'
        }
        if config.last_processed_ts:
            params['oldest'] = config.last_processed_ts

        response = slack_curl('GET', 'conversations.history', params)
    else:
        # Use conversations.replies for thread monitoring
        params = {
            'channel': config.channel_id,
            'ts': config.thread_ts,
            'oldest': config.last_processed_ts if config.last_processed_ts else config.thread_ts
        }
        response = slack_curl('GET', 'conversations.replies', params)

    if not response or not response.get('ok'):
        return None

    messages = response.get('messages', [])
    bot_user_id = os.getenv('SLACK_BOT_USER_ID', 'U0AJ2HHU2KT')

    # Find mentions after last_processed_ts
    for msg in messages:
        msg_ts = msg.get('ts', '')

        # Skip if we've already processed this
        if config.last_processed_ts and msg_ts <= config.last_processed_ts:
            continue

        # Skip bot's own messages
        if msg.get('user') == bot_user_id or msg.get('bot_id'):
            continue

        text = msg.get('text', '')

        # Check for @mention or keyword
        if f'<@{bot_user_id}>' in text or 'sutra' in text.lower():
            logger.info(f"Found new mention: {msg_ts}")
            return {
                'ts': msg_ts,
                'text': text,
                'user': msg.get('user', 'unknown')
            }

    return None


def post_to_thread(config: SlackAgentConfig, text: str, reply_to_ts: Optional[str] = None) -> bool:
    """Post a message to Slack, optionally as a thread reply."""
    if not config.channel_id:
        logger.error("No channel configured")
        return False

    data = {
        'channel': config.channel_id,
        'text': text
    }

    # Determine thread_ts for reply
    # Priority: reply_to_ts (for channel monitoring) > config.thread_ts (for thread monitoring)
    thread_ts = reply_to_ts or config.thread_ts
    if thread_ts and thread_ts != "channel":
        data['thread_ts'] = thread_ts

    response = slack_curl('POST', 'chat.postMessage', data)
    if response and response.get('ok'):
        logger.info(f"Posted to Slack thread: {len(text)} chars")
        return True
    else:
        logger.error(f"Failed to post to Slack")
        return False


def format_slack_message_for_agent(mention: Dict) -> str:
    """Format a Slack mention as a prompt for the agent."""
    text = mention.get('text', '')
    # Strip the @mention itself
    bot_user_id = os.getenv('SLACK_BOT_USER_ID', 'U0AJ2HHU2KT')
    text = text.replace(f'<@{bot_user_id}>', '').strip()

    return f"[Slack] {text}"


def clean_response_for_slack(response: str) -> str:
    """Clean agent response for posting to Slack.

    Removes terminal escape codes, tool output, etc.
    """
    import re

    # Remove ANSI escape codes
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', response)

    # Remove common terminal artifacts
    text = text.replace('\r', '')

    # Find the actual response content (heuristic: after the prompt, before next prompt)
    # This is tricky - we'll look for the agent's actual text output
    lines = text.split('\n')

    # Filter out lines that look like terminal UI
    clean_lines = []
    for line in lines:
        # Skip empty lines at start/end
        stripped = line.strip()
        if not stripped:
            continue
        # Skip lines that look like prompts or UI
        if stripped.startswith('>') or stripped.startswith('$'):
            continue
        if 'Cost:' in line or 'tokens' in line.lower():
            continue
        clean_lines.append(stripped)

    result = '\n'.join(clean_lines)

    # Truncate if too long
    if len(result) > 2000:
        result = result[:1997] + '...'

    return result.strip()


class SlackAgentLoop:
    """Manages the Slack agent polling and response loop."""

    def __init__(self, pty_manager, get_agent_func):
        self.pty_manager = pty_manager
        self.get_agent = get_agent_func  # Function to get agent by ID from db
        self.config = SlackAgentConfig.load()
        self.output_buffer = ""
        self.last_output_time = 0
        self.response_start_time = 0
        self.scrollback_start_len = 0  # Track scrollback position when we inject
        self.last_scrollback_len = 0   # Track scrollback for idle detection
        self._lock = asyncio.Lock()

    def set_agent(self, agent_id: str):
        """Set which agent handles Slack messages."""
        self.config.agent_id = agent_id
        self.config.save()
        logger.info(f"Slack agent set to: {agent_id}")

    def set_thread(self, channel_id: str, thread_ts: str):
        """Set the Slack thread to monitor."""
        self.config.channel_id = channel_id
        self.config.thread_ts = thread_ts
        self.config.save()
        logger.info(f"Slack thread set: {channel_id}/{thread_ts}")

    def on_agent_output(self, agent_id: str, data: bytes):
        """Called when the Slack agent produces output."""
        if agent_id != self.config.agent_id:
            return
        if self.config.state != SlackAgentState.WAITING_RESPONSE.value:
            return

        try:
            text = data.decode('utf-8', errors='ignore')
            self.output_buffer += text
            self.last_output_time = time.time()
            # Keep buffer reasonable
            if len(self.output_buffer) > 10000:
                self.output_buffer = self.output_buffer[-10000:]
        except Exception as e:
            logger.debug(f"Output capture error: {e}")

    async def check_response_complete(self) -> bool:
        """Check if the agent has finished responding (idle)."""
        if self.config.state != SlackAgentState.WAITING_RESPONSE.value:
            return False

        # Check for timeout
        elapsed = time.time() - self.response_start_time
        if elapsed > RESPONSE_TIMEOUT:
            logger.warning(f"Response timeout after {elapsed:.0f}s")
            # Capture whatever we have from scrollback
            self._capture_from_scrollback()
            return True

        # Read current scrollback to detect new output
        scrollback = self.pty_manager.get_scrollback(self.config.agent_id)
        current_len = len(scrollback)

        if current_len > self.last_scrollback_len:
            # New output detected
            self.last_output_time = time.time()
            self.last_scrollback_len = current_len
            logger.debug(f"New output detected: {current_len - self.scrollback_start_len} bytes since inject")
            return False

        # Check for idle (no output for IDLE_THRESHOLD seconds)
        if self.last_output_time > 0:
            idle_time = time.time() - self.last_output_time
            if idle_time > IDLE_THRESHOLD:
                logger.info(f"Agent idle for {idle_time:.1f}s - response complete")
                self._capture_from_scrollback()
                return True

        return False

    def _capture_from_scrollback(self):
        """Capture response from PTY scrollback buffer."""
        scrollback = self.pty_manager.get_scrollback(self.config.agent_id)
        if len(scrollback) > self.scrollback_start_len:
            new_output = scrollback[self.scrollback_start_len:]
            try:
                self.output_buffer = new_output.decode('utf-8', errors='ignore')
                logger.info(f"Captured {len(self.output_buffer)} chars from scrollback")
            except Exception as e:
                logger.error(f"Error decoding scrollback: {e}")
                self.output_buffer = ""

    async def inject_message(self, prompt: str) -> bool:
        """Inject a message into the agent's PTY."""
        if not self.config.agent_id:
            logger.error("No Slack agent configured")
            return False

        if not self.pty_manager.has_session(self.config.agent_id):
            logger.error(f"Agent {self.config.agent_id} has no active PTY session")
            return False

        # Record scrollback position before injection
        scrollback = self.pty_manager.get_scrollback(self.config.agent_id)
        self.scrollback_start_len = len(scrollback)
        self.last_scrollback_len = self.scrollback_start_len
        logger.info(f"Scrollback position before inject: {self.scrollback_start_len}")

        # Type the message character by character (like orchestrator_cron)
        for ch in prompt:
            if not self.pty_manager.write(self.config.agent_id, ch.encode('utf-8')):
                return False
            await asyncio.sleep(0.005)

        # Press Enter
        if not self.pty_manager.write(self.config.agent_id, b'\r'):
            return False

        logger.info(f"Injected message to agent: {prompt[:50]}...")
        return True

    async def poll_and_respond(self):
        """Main polling loop - called periodically."""
        async with self._lock:
            await self._poll_and_respond_locked()

    async def _poll_and_respond_locked(self):
        """Locked implementation of poll/respond logic."""
        state = SlackAgentState(self.config.state)

        # === STATE: IDLE - check for new mentions ===
        if state == SlackAgentState.IDLE:
            # Rate limit polling
            if time.time() - self.config.last_poll_time < POLL_INTERVAL:
                return

            self.config.last_poll_time = time.time()

            mention = get_new_mentions(self.config)
            if not mention:
                logger.debug("No new mentions")
                return

            # Found a mention - transition to PROCESSING
            self.config.state = SlackAgentState.PROCESSING.value
            self.config.current_message_ts = mention['ts']
            self.config.save()

            logger.info(f"Processing mention: {mention['ts']}")

            # Format and inject
            prompt = format_slack_message_for_agent(mention)
            self.output_buffer = ""
            self.last_output_time = 0

            success = await self.inject_message(prompt)
            if success:
                self.config.state = SlackAgentState.WAITING_RESPONSE.value
                self.response_start_time = time.time()
                self.config.save()
                logger.info("Waiting for agent response...")
            else:
                # Failed to inject - go back to idle
                logger.error("Failed to inject message")
                self.config.state = SlackAgentState.IDLE.value
                self.config.save()

        # === STATE: WAITING_RESPONSE - check if agent is done ===
        elif state == SlackAgentState.WAITING_RESPONSE:
            if await self.check_response_complete():
                # Transition to POSTING
                self.config.state = SlackAgentState.POSTING.value
                self.config.response_buffer = self.output_buffer
                self.config.save()

                # Clean and post response
                response = clean_response_for_slack(self.output_buffer)
                if response:
                    # Reply to the original message that mentioned us
                    success = post_to_thread(self.config, response, self.config.current_message_ts)
                    if success:
                        logger.info("Response posted to Slack")
                    else:
                        logger.error("Failed to post response")
                else:
                    logger.warning("No response to post (empty after cleaning)")

                # Mark as processed and return to IDLE
                self.config.last_processed_ts = self.config.current_message_ts
                self.config.current_message_ts = ""
                self.config.state = SlackAgentState.IDLE.value
                self.config.response_buffer = ""
                self.config.save()

                logger.info("Returned to IDLE state")

        # === STATE: PROCESSING or POSTING - wait ===
        else:
            logger.debug(f"In state {state.value}, waiting...")


# Singleton instance (initialized by ws_server)
_slack_agent_loop: Optional[SlackAgentLoop] = None


def get_slack_agent_loop() -> Optional[SlackAgentLoop]:
    """Get the singleton SlackAgentLoop instance."""
    return _slack_agent_loop


def init_slack_agent_loop(pty_manager, get_agent_func) -> SlackAgentLoop:
    """Initialize the Slack agent loop."""
    global _slack_agent_loop
    _slack_agent_loop = SlackAgentLoop(pty_manager, get_agent_func)
    return _slack_agent_loop
