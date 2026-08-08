#!/usr/bin/env python3
# -*- coding: ascii -*-

import os
import sys
import json
import signal
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path.home() / '.loreconvo'
QUEUE_DIR = BASE_DIR / 'capture_queue'
LOG_DIR = BASE_DIR / 'capture_log'
STATE_PATH = BASE_DIR / 'capture_state.json'

def load_state():
    try:
        with open(STATE_PATH, 'r', encoding='ascii') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {
            'tool_call_count': 0,
            'daily_haiku_calls': 0,
            'daily_date_utc': None,
            'worker_not_found_warned': False
        }

def save_state(state):
    try:
        with open(STATE_PATH, 'w', encoding='ascii') as f:
            json.dump(state, f, separators=(',', ':'))
        os.chmod(STATE_PATH, 0o600)
    except Exception:
        pass

def is_pro_tier():
    if os.environ.get('LORECONVO_PRO_LICENSE', '').lower() == 'true':
        return True
    try:
        from loreconvo.core.tier_manager import TierManager
        return TierManager().is_pro()
    except ImportError:
        return False

def get_daily_limit():
    try:
        return int(os.environ.get('LORECONVO_TURN_CAPTURE_MAX_CALLS_PER_DAY', '100'))
    except ValueError:
        return 100

def call_haiku(excerpt):
    try:
        from anthropic import Anthropic
    except ImportError:
        return excerpt

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return excerpt

    try:
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model='claude-3-5-haiku-20241022',
            max_tokens=100,
            messages=[{
                'role': 'user',
                'content': f'Summarize this conversation excerpt in 100 tokens or less, focusing on key decisions and new information:\n\n{excerpt}'
            }],
            timeout=5.0
        )
        return response.content[0].text
    except Exception:
        return excerpt

def read_queue_entries(queue_file):
    entries = []
    try:
        with open(queue_file, 'r', encoding='ascii') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get('type') == 'queued':
                        entries.append(entry)
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return entries

def write_capture_log(ts, turn_estimate, summary, session_id, surface):
    today = datetime.now(timezone.utc).strftime('%Y%m%d')
    log_file = LOG_DIR / f'{today}.jsonl'
    try:
        LOG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        entry = {
            'type': 'capture',
            'ts': ts,
            'turn_estimate': turn_estimate,
            'summary': summary,
            'session_id': session_id,
            'surface': surface,
            'user_id': None
        }
        with open(log_file, 'a', encoding='ascii') as f:
            f.write(json.dumps(entry, separators=(',', ':')) + '\n')
        os.chmod(log_file, 0o600)
        return True
    except Exception:
        return False

def mark_processed(queue_file, orig_ts, session_id):
    try:
        marker = {
            'type': 'processed',
            'orig_ts': orig_ts,
            'session_id': session_id
        }
        with open(queue_file, 'a', encoding='ascii') as f:
            f.write(json.dumps(marker, separators=(',', ':')) + '\n')
    except Exception:
        pass

def prune_old_logs(directory, max_days=7):
    try:
        cutoff = (datetime.now(timezone.utc).date() - timedelta(days=max_days))
        for f in directory.iterdir():
            if f.name.endswith('.jsonl') and len(f.stem) == 8:
                try:
                    file_date = datetime.strptime(f.stem, '%Y%m%d').date()
                    if file_date < cutoff:
                        f.unlink()
                except Exception:
                    pass
    except Exception:
        pass

def lock_queue_file(queue_file):
    if sys.platform == 'win32':
        try:
            import portalocker
            return open(queue_file, 'a', encoding='ascii')
        except ImportError:
            return None
    else:
        import fcntl
        try:
            f = open(queue_file, 'a', encoding='ascii')
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            return f
        except Exception:
            return None

def unlock_queue_file(f):
    if f:
        if sys.platform == 'win32':
            try:
                import portalocker
                portalocker.unlock(f)
            except Exception:
                pass
        else:
            try:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
        f.close()

def main():
    try:
        QUEUE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        LOG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

        state = load_state()
        today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        if state.get('daily_date_utc') != today_utc:
            state['daily_haiku_calls'] = 0
            state['daily_date_utc'] = today_utc

        pro = is_pro_tier()
        daily_limit = get_daily_limit()

        for queue_file in QUEUE_DIR.glob('*.jsonl'):
            lock = lock_queue_file(queue_file)
            try:
                entries = read_queue_entries(queue_file)
                for entry in entries:
                    excerpt = entry.get('excerpt', '')
                    session_id = entry.get('session_id', '')
                    surface = entry.get('surface', 'code')
                    ts = entry.get('ts', '')

                    summary = excerpt
                    if pro and state['daily_haiku_calls'] < daily_limit:
                        summary = call_haiku(excerpt)
                        state['daily_haiku_calls'] += 1

                    write_capture_log(ts, 1, summary, session_id, surface)
                    mark_processed(queue_file, ts, session_id)
            finally:
                unlock_queue_file(lock)

        prune_old_logs(QUEUE_DIR, 7)
        prune_old_logs(LOG_DIR, 7)
        save_state(state)

    except Exception:
        pass

    return 0

if __name__ == '__main__':
    sys.exit(main())
