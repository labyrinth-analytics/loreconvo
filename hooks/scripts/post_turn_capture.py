#!/usr/bin/env python3
# -*- coding: ascii -*-

import os
import sys
import json
import uuid
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

STATE_PATH = Path.home() / '.loreconvo' / 'capture_state.json'
QUEUE_DIR = Path.home() / '.loreconvo' / 'capture_queue'
MAX_DAYS_OLD = 7

def load_state():
    try:
        with open(STATE_PATH, 'r', encoding='ascii') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        now_utc = datetime.now(timezone.utc)
        return {
            'session_id': str(uuid.uuid4()),
            'tool_call_count': 0,
            'daily_haiku_calls': 0,
            'daily_date_utc': now_utc.strftime('%Y-%m-%d'),
            'worker_not_found_warned': False
        }

def save_state(state):
    try:
        STATE_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with open(STATE_PATH, 'w', encoding='ascii') as f:
            json.dump(state, f, separators=(',', ':'))
        os.chmod(STATE_PATH, 0o600)
    except Exception:
        pass

def read_transcript():
    transcript_path = os.environ.get('CLAUDE_TRANSCRIPT_PATH')
    if transcript_path:
        try:
            with open(transcript_path, 'r', encoding='ascii', errors='replace') as f:
                content = f.read()
                return content[-500:] if len(content) > 500 else content
        except Exception:
            pass
    try:
        content = sys.stdin.read()
        return content[-500:] if len(content) > 500 else content
    except Exception:
        return ''

def write_queue_entry(entry_dict):
    utc_date = datetime.now(timezone.utc).strftime('%Y%m%d')
    queue_file = QUEUE_DIR / f'{utc_date}.jsonl'
    try:
        QUEUE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        line = json.dumps(entry_dict, separators=(',', ':')) + '\n'
        if sys.platform == 'win32':
            try:
                import portalocker
                with open(queue_file, 'a', encoding='ascii') as f:
                    portalocker.lock(f, portalocker.LOCK_EX)
                    f.write(line)
            except ImportError:
                pass
        else:
            import fcntl
            with open(queue_file, 'a', encoding='ascii') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.write(line)
    except Exception:
        pass

def prune_old_queues():
    try:
        cutoff = (datetime.now(timezone.utc).date() - timedelta(days=MAX_DAYS_OLD))
        for f in QUEUE_DIR.iterdir():
            if f.name.endswith('.jsonl') and len(f.stem) == 8:
                try:
                    file_date = datetime.strptime(f.stem, '%Y%m%d').date()
                    if file_date < cutoff:
                        f.unlink()
                except Exception:
                    pass
    except Exception:
        pass

def spawn_worker(state):
    try:
        subprocess.Popen(
            ['loreconvo-capture-worker'],
            start_new_session=True,
            close_fds=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except FileNotFoundError:
        if not state.get('worker_not_found_warned', False):
            sys.stderr.write('[LORECONVO-WARN] loreconvo-capture-worker not found -- captures are being queued but will NOT be summarized until the worker is installed (pip install --force-reinstall loreconvo)\n')
            sys.stderr.flush()
            state['worker_not_found_warned'] = True
            save_state(state)
    except Exception:
        pass

def main():
    capture_enabled = os.environ.get('LORECONVO_POST_TURN_CAPTURE', '') == '1'
    if not capture_enabled:
        return 0

    if sys.platform == 'win32':
        try:
            import portalocker
        except ImportError:
            return 0

    try:
        state = load_state()
        env_sid = os.environ.get('LORECONVO_AGENT_RUN_SESSION_ID')
        if env_sid and state['session_id'] != env_sid:
            state['session_id'] = env_sid

        state['tool_call_count'] += 1
        save_state(state)

        interval = int(os.environ.get('LORECONVO_TURN_CAPTURE_INTERVAL', '10'))
        if state['tool_call_count'] % interval != 0:
            return 0

        excerpt = read_transcript()
        if not excerpt:
            return 0

        entry = {
            'type': 'queued',
            'ts': datetime.now(timezone.utc).isoformat(),
            'excerpt': excerpt,
            'session_id': state['session_id'],
            'surface': os.environ.get('LORECONVO_SURFACE', 'code')
        }

        write_queue_entry(entry)
        prune_old_queues()
        spawn_worker(state)

    except Exception:
        pass

    return 0

if __name__ == '__main__':
    sys.exit(main())
