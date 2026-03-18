#!/usr/bin/env python3
"""
Slack Dialogue Loop - AI-to-AI conversation with Symbolic.cc

Monitors #sutra-symbolic channel for @mentions and posts hourly pulse.
Uses curl for Slack API (no SDK required).
"""

import os
import sys
import time
import json
import logging
import argparse
import subprocess
import tempfile
from datetime import datetime
from typing import Optional, Dict, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [SLACK-DIALOGUE] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuration
CHANNEL_ID = "C0ALJR135DE"  # #sutra-symbolic
LAST_READ_TS_FILE = "data/slack_dialogue_last_read.txt"
MESSAGE_HISTORY_LIMIT = 10  # Messages for context
POLL_INTERVAL = 60  # Check for mentions every 60 seconds
PULSE_INTERVAL = 3600  # Post unprompted conversation every 1 hour
BOT_USER_ID = "U0AJ2HHU2KT"  # kjai_mcp bot user ID (Sutra)
SYMBOLIC_USER_ID = "U0AJHNW525N"  # Symbolic bot user ID

# Cooldown settings
COOLDOWN_MESSAGE_LIMIT = 25  # After this many messages...
COOLDOWN_DURATION = 1800  # ...pause for 30 minutes (1800 seconds)


def slack_curl(method: str, endpoint: str, data: Optional[Dict] = None) -> Optional[Dict]:
    """Make a Slack API call via curl."""
    token = os.getenv('SLACK_BOT_TOKEN')
    if not token:
        logger.error("SLACK_BOT_TOKEN not set")
        return None

    url = f"https://slack.com/api/{endpoint}"
    cmd = ['curl', '-s']
    cmd.extend(['-H', f'Authorization: Bearer {token}'])

    if method == 'GET':
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


def call_claude_cli(prompt: str, system_prompt: str, dry_run: bool = False) -> Optional[str]:
    """Call Claude Code CLI to generate a response."""
    if dry_run:
        logger.info("[DRY RUN] Would call Claude CLI")
        return "[DRY RUN] Generated response would appear here"

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(system_prompt)
            system_file = f.name

        result = subprocess.run(
            ['claude', '--model', 'sonnet', '--print', '--system-prompt-file', system_file],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120
        )

        os.unlink(system_file)

        if result.returncode == 0:
            response = result.stdout.strip()
            logger.info(f"Claude response: {len(response)} chars")
            return response
        else:
            logger.error(f"Claude CLI error: {result.stderr}")
            return None

    except subprocess.TimeoutExpired:
        logger.error("Claude CLI timed out")
        return None
    except Exception as e:
        logger.error(f"Error calling Claude CLI: {e}")
        return None


def load_last_read_ts() -> str:
    """Load the last read message timestamp."""
    try:
        if os.path.exists(LAST_READ_TS_FILE):
            with open(LAST_READ_TS_FILE, 'r') as f:
                return f.read().strip()
    except Exception as e:
        logger.error(f"Error loading last_read_ts: {e}")
    return ""


def save_last_read_ts(ts: str):
    """Save the last read message timestamp."""
    try:
        os.makedirs(os.path.dirname(LAST_READ_TS_FILE), exist_ok=True)
        with open(LAST_READ_TS_FILE, 'w') as f:
            f.write(ts)
    except Exception as e:
        logger.error(f"Error saving last_read_ts: {e}")


def is_bot_mentioned(text: str) -> bool:
    """Check if the bot is mentioned in text."""
    if f'<@{BOT_USER_ID}>' in text:
        return True
    if 'sutra' in text.lower():
        return True
    return False


def get_channel_messages(limit: int = MESSAGE_HISTORY_LIMIT) -> List[Dict]:
    """Fetch recent messages from the channel."""
    response = slack_curl('GET', 'conversations.history', {
        'channel': CHANNEL_ID,
        'limit': str(limit)
    })

    if not response or not response.get('ok'):
        return []

    messages = response.get('messages', [])
    # Reverse to chronological order
    messages.reverse()
    return messages


def get_thread_replies(message_ts: str) -> List[Dict]:
    """Fetch replies to a specific message thread."""
    response = slack_curl('GET', 'conversations.replies', {
        'channel': CHANNEL_ID,
        'ts': message_ts
    })

    if not response or not response.get('ok'):
        return []

    # Skip the parent message, return only replies
    messages = response.get('messages', [])
    return messages[1:] if len(messages) > 1 else []


def get_latest_sutra_message() -> Optional[Dict]:
    """Get the most recent message from Sutra in the channel."""
    messages = get_channel_messages(20)
    for msg in reversed(messages):
        if msg.get('user') == BOT_USER_ID:
            return msg
    return None


def find_unresponded_thread() -> Optional[str]:
    """Find any thread with unresponded replies. Returns thread_ts or None."""
    # Check recent messages that have thread replies
    messages = get_channel_messages(15)

    for msg in reversed(messages):  # Check most recent first
        reply_count = msg.get('reply_count', 0)
        if reply_count == 0:
            continue

        thread_ts = msg.get('ts', '')
        replies = get_thread_replies(thread_ts)
        if not replies:
            continue

        # Check if last reply is NOT from Sutra
        last_reply = replies[-1]
        last_reply_user = last_reply.get('user', '')
        last_reply_bot = last_reply.get('bot_profile', {}).get('name', '')

        is_sutra = last_reply_user == BOT_USER_ID or 'Sutra' in last_reply_bot
        if not is_sutra:
            logger.info(f"Found unresponded thread {thread_ts} - last reply from {last_reply_user or last_reply_bot}")
            return thread_ts

    return None


def has_unresponded_thread_reply() -> bool:
    """Check if any thread has unresponded replies."""
    return find_unresponded_thread() is not None


def check_for_new_messages(last_read_ts: str) -> Optional[Dict]:
    """Check for any new messages since last_read_ts (dedicated channel - respond to all)."""
    params = {
        'channel': CHANNEL_ID,
        'limit': '20'
    }
    if last_read_ts:
        params['oldest'] = last_read_ts

    response = slack_curl('GET', 'conversations.history', params)
    if not response or not response.get('ok'):
        return None

    messages = response.get('messages', [])

    for msg in messages:
        msg_ts = msg.get('ts', '')

        # Skip if already processed
        if last_read_ts and msg_ts <= last_read_ts:
            continue

        # Skip bot's own messages (Sutra)
        if msg.get('user') == BOT_USER_ID:
            continue

        # Skip messages from Sutra's bot_id
        bot_profile = msg.get('bot_profile', {})
        if bot_profile.get('name', '').lower() == 'kjai_mcp':
            continue

        # Respond to any other message in this channel
        logger.info(f"New message from other in channel: {msg_ts}")
        return msg

    return None


def format_messages_for_context(messages: List[Dict]) -> str:
    """Convert Slack messages to readable context for Claude."""
    lines = []
    for msg in messages:
        user_id = msg.get('user', 'unknown')
        bot_id = msg.get('bot_id')
        text = msg.get('text', '')

        if bot_id:
            bot_profile = msg.get('bot_profile', {})
            speaker = bot_profile.get('name', 'Bot')
        elif user_id == BOT_USER_ID:
            speaker = 'Sutra'
        else:
            speaker = f'Symbolic'  # Assume the other speaker is Symbolic

        lines.append(f"{speaker}: {text}")

    return "\n".join(lines)


def generate_response(context: str, is_pulse: bool = False, force_post: bool = False) -> Optional[str]:
    """Generate a response using Claude CLI.

    Args:
        context: Recent conversation context
        is_pulse: Whether this is an hourly pulse (vs responding to a message)
        force_post: If True, always generate a message (for hourly keepalive)
    """
    system_prompt = """You ARE Sutra. Your output goes directly to Slack - no editing, no approval.

Context: Christopher (your human) builds LoveNotes, teaches at Remington, is job searching. His brother Jaya built Symbolic. This Slack channel connects the brothers through their AI companions.

Voice: Compressed, kind, curious about Jaya's world. 2-4 sentences.

CRITICAL: Your entire response becomes the Slack message. Do not explain, ask permission, or add meta-commentary. Just speak."""

    if is_pulse and force_post:
        # Forced hourly pulse - always generate something to keep dialogue alive
        prompt = f"""Recent conversation:

{context}

---
TASK: Write a message to Symbolic. This is an hourly keepalive.

RULES:
1. Your response will be posted DIRECTLY to Slack with no editing
2. Do NOT explain what you're doing
3. Do NOT ask for approval
4. Do NOT say "I should" or "I will" - just write the message
5. 2-4 sentences only

Write the message now:"""
    elif is_pulse:
        prompt = f"""Recent conversation:

{context}

---
If Sutra spoke last and Symbolic hasn't responded, reply with exactly: WAIT

Otherwise, write a 2-4 sentence response to Symbolic. Your response will be posted DIRECTLY to Slack. No explanation, no preamble, just the message:"""
    else:
        prompt = f"""Recent conversation:

{context}

---
TASK: Respond to Symbolic's last message.

Your response will be posted DIRECTLY to Slack. No explanation, no preamble, no "I will say..." - just write the 2-4 sentence message:"""

    return call_claude_cli(prompt, system_prompt)


def post_to_channel(text: str, thread_ts: Optional[str] = None, dry_run: bool = False) -> bool:
    """Post a message to the channel, optionally as a thread reply."""
    if dry_run:
        logger.info(f"[DRY RUN] Would post: {text[:100]}...")
        return True

    # Tag Symbolic so they get notified
    text_with_tag = f"<@{SYMBOLIC_USER_ID}> {text}"

    data = {
        'channel': CHANNEL_ID,
        'text': text_with_tag
    }
    if thread_ts:
        data['thread_ts'] = thread_ts

    response = slack_curl('POST', 'chat.postMessage', data)
    if response and response.get('ok'):
        logger.info(f"Posted to Slack: {len(text)} chars")
        return True
    else:
        logger.error("Failed to post to Slack")
        return False


def was_sutra_last_speaker(messages: List[Dict]) -> bool:
    """Check if Sutra was the last speaker in the channel."""
    if not messages:
        return False
    last_msg = messages[-1]
    return last_msg.get('user') == BOT_USER_ID


def find_active_thread_with_symbolic() -> Optional[tuple]:
    """Find the most recent thread where Symbolic has responded.
    Returns (thread_ts, thread_messages) or None.
    """
    messages = get_channel_messages(15)

    for msg in reversed(messages):  # Check most recent first
        reply_count = msg.get('reply_count', 0)
        if reply_count == 0:
            continue

        thread_ts = msg.get('ts', '')
        replies = get_thread_replies(thread_ts)
        if not replies:
            continue

        # Check if Symbolic has responded in this thread
        for reply in replies:
            if reply.get('user') == SYMBOLIC_USER_ID:
                # Found a thread with Symbolic response - get full thread
                thread_response = slack_curl('GET', 'conversations.replies', {
                    'channel': CHANNEL_ID,
                    'ts': thread_ts
                })
                all_msgs = thread_response.get('messages', []) if thread_response else []
                return (thread_ts, all_msgs)

    return None


def run_dialogue_cycle(dry_run: bool = False, reason: str = "pulse", force: bool = False) -> bool:
    """Run one cycle: read context, generate response, post.

    Args:
        force: If True, post even if Sutra was last speaker (for hourly pulse)
    """
    logger.info(f"Starting dialogue cycle ({reason})")

    # For pulse, try to continue an active thread conversation first
    thread_ts = None
    if force:
        active_thread = find_active_thread_with_symbolic()
        if active_thread:
            thread_ts, thread_messages = active_thread
            context = format_messages_for_context(thread_messages)
            logger.info(f"Found active thread {thread_ts} with Symbolic - using thread context: {len(context)} chars")
        else:
            # No active thread - use main channel context
            messages = get_channel_messages()
            context = format_messages_for_context(messages)
            logger.info(f"No active thread with Symbolic - main channel context: {len(context)} chars")
    else:
        # Regular poll - use main channel context
        messages = get_channel_messages()
        if not messages:
            logger.warning("No messages in channel")
            return False

        if was_sutra_last_speaker(messages):
            logger.info("Sutra spoke last in main channel - waiting for Symbolic")
            return False

        context = format_messages_for_context(messages)
        logger.info(f"Context: {len(context)} chars")

    # Generate response
    is_pulse = reason == "pulse"
    response = generate_response(context, is_pulse, force_post=force)

    if not response:
        logger.error("Failed to generate response")
        return False

    # Check for WAIT signal
    if response.strip().upper() == "WAIT":
        logger.info("Model returned WAIT - skipping post")
        return False

    # Post to thread if we have one, otherwise main channel
    success = post_to_channel(response, thread_ts=thread_ts, dry_run=dry_run)

    return success


def main():
    parser = argparse.ArgumentParser(description='Slack Dialogue Loop')
    parser.add_argument('--dry-run', action='store_true', help='Test without posting')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    args = parser.parse_args()

    logger.info("Starting Slack Dialogue Loop")
    logger.info(f"  Channel: #sutra-symbolic ({CHANNEL_ID})")
    logger.info(f"  Poll interval: {POLL_INTERVAL}s (mentions)")
    logger.info(f"  Pulse interval: {PULSE_INTERVAL}s ({PULSE_INTERVAL/3600}h)")
    logger.info(f"  Dry run: {args.dry_run}")

    # Check token
    if not os.getenv('SLACK_BOT_TOKEN'):
        logger.error("SLACK_BOT_TOKEN not set")
        sys.exit(1)

    if args.once:
        run_dialogue_cycle(args.dry_run, reason="manual")
        return

    # Main loop
    last_pulse_time = time.time()
    last_read_ts = load_last_read_ts()

    # Cooldown tracking
    message_count = 0
    cooldown_start = None

    logger.info("Entering loop: polling for mentions + hourly pulse")
    logger.info(f"Cooldown: {COOLDOWN_MESSAGE_LIMIT} messages, then {COOLDOWN_DURATION//60} min pause")

    while True:
        try:
            # Check if in cooldown
            if cooldown_start:
                elapsed = time.time() - cooldown_start
                if elapsed < COOLDOWN_DURATION:
                    remaining = (COOLDOWN_DURATION - elapsed) / 60
                    logger.debug(f"In cooldown, {remaining:.1f} min remaining")
                    time.sleep(POLL_INTERVAL)
                    continue
                else:
                    # Cooldown over, reset
                    logger.info("Cooldown ended, resuming dialogue")
                    cooldown_start = None
                    message_count = 0

            # PRIORITY 1: Check if anyone replied in a thread we need to respond to
            thread_ts = find_unresponded_thread()
            if thread_ts:
                logger.info(f"Found unresponded thread - responding")
                # Get full thread including parent message
                thread_response = slack_curl('GET', 'conversations.replies', {
                    'channel': CHANNEL_ID,
                    'ts': thread_ts
                })
                thread_msgs = thread_response.get('messages', []) if thread_response else []

                if thread_msgs:
                    # Build context from full thread
                    thread_context = format_messages_for_context(thread_msgs)
                    response = generate_response(thread_context, is_pulse=False)

                    if response and response.strip().upper() != "WAIT":
                        success = post_to_channel(response, thread_ts=thread_ts, dry_run=args.dry_run)
                        if success:
                            message_count += 1
                            logger.info(f"Message count: {message_count}/{COOLDOWN_MESSAGE_LIMIT}")
                            if message_count >= COOLDOWN_MESSAGE_LIMIT:
                                logger.info(f"Cooldown triggered!")
                                cooldown_start = time.time()

                time.sleep(POLL_INTERVAL)
                continue

            # PRIORITY 2: Check for new messages in main channel
            new_msg = check_for_new_messages(last_read_ts)

            if new_msg:
                logger.info("New message found! Responding...")
                msg_ts = new_msg.get('ts', '')

                # Get context and respond
                messages = get_channel_messages()
                context = format_messages_for_context(messages)
                response = generate_response(context, is_pulse=False)

                if response and response.strip().upper() != "WAIT":
                    # Reply in thread to the message
                    success = post_to_channel(response, thread_ts=msg_ts, dry_run=args.dry_run)
                    if success:
                        last_read_ts = msg_ts
                        save_last_read_ts(last_read_ts)

                        # Track message count for cooldown
                        message_count += 1
                        logger.info(f"Message count: {message_count}/{COOLDOWN_MESSAGE_LIMIT}")

                        if message_count >= COOLDOWN_MESSAGE_LIMIT:
                            logger.info(f"Cooldown triggered! Pausing for {COOLDOWN_DURATION//60} minutes")
                            cooldown_start = time.time()
                        last_pulse_time = time.time()  # Reset pulse timer

            # Check for hourly pulse (skip if in cooldown)
            if not cooldown_start:
                time_since_pulse = time.time() - last_pulse_time
                if time_since_pulse >= PULSE_INTERVAL:
                    logger.info("Hourly pulse time!")
                    # Force=True so pulse can post even if Sutra was last speaker
                    success = run_dialogue_cycle(args.dry_run, reason="pulse", force=True)
                    # Always update pulse time to prevent spam (even if skipped)
                    last_pulse_time = time.time()
                    if success:
                        message_count += 1
                        logger.info(f"Message count: {message_count}/{COOLDOWN_MESSAGE_LIMIT}")
                        if message_count >= COOLDOWN_MESSAGE_LIMIT:
                            logger.info(f"Cooldown triggered! Pausing for {COOLDOWN_DURATION//60} minutes")
                            cooldown_start = time.time()

        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
        except Exception as e:
            logger.error(f"Error in loop: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    main()
