#!/usr/bin/env python3
# -*- coding: ascii -*-

import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path


BASE_DIR = Path.home() / '.loreconvo'
QUEUE_DIR = BASE_DIR / 'capture_queue'
LOG_DIR = BASE_DIR / 'capture_log'
STATE_PATH = BASE_DIR / 'capture_state.json'
STATE_LOCK_PATH = BASE_DIR / '.capture_state.lock'


def load_state():
    try:
        with open(STATE_PATH, 'r', encoding='ascii') as state_file:
            return json.load(state_file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {
            'tool_call_count': 0,
            'daily_haiku_calls': 0,
            'daily_date_utc': None,
            'worker_not_found_warned': False,
        }


def save_state(state):
    temp_path = None
    try:
        STATE_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(STATE_PATH.parent, 0o700)
        fd, temp_name = tempfile.mkstemp(
            dir=str(STATE_PATH.parent), prefix='.capture_state.', suffix='.tmp')
        temp_path = Path(temp_name)
        with os.fdopen(fd, 'w', encoding='ascii') as state_file:
            json.dump(state, state_file, separators=(',', ':'))
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, STATE_PATH)
        return True
    except Exception:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
        return False


def is_pro_tier():
    try:
        from core.config import Config
    except ImportError:
        try:
            from loreconvo.core.config import Config
        except ImportError:
            return False
    return Config().is_pro


def get_daily_limit():
    try:
        return max(0, int(os.environ.get(
            'LORECONVO_TURN_CAPTURE_MAX_CALLS_PER_DAY', '100')))
    except ValueError:
        return 100


def haiku_available():
    if not os.environ.get('ANTHROPIC_API_KEY'):
        return False
    try:
        from anthropic import Anthropic  # noqa: F401
    except ImportError:
        return False
    return True


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
                'content': (
                    'Summarize this conversation excerpt in 100 tokens or less, '
                    'focusing on key decisions and new information:\n\n'
                    f'{excerpt}'
                ),
            }],
            timeout=5.0,
        )
        return response.content[0].text
    except Exception:
        return excerpt


def _read_queue_lines(queue_source):
    if hasattr(queue_source, 'read'):
        queue_source.seek(0)
        return queue_source.readlines()
    with open(queue_source, 'r', encoding='ascii') as queue_file:
        return queue_file.readlines()


def read_queue_entries(queue_source):
    parsed = []
    try:
        for line in _read_queue_lines(queue_source):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                parsed.append(entry)
    except Exception:
        return []

    processed = {
        (entry.get('orig_ts'), entry.get('session_id'))
        for entry in parsed
        if entry.get('type') == 'processed'
        and entry.get('orig_ts') is not None
        and entry.get('session_id') is not None
    }
    entries = []
    seen = set()
    for entry in parsed:
        if entry.get('type') != 'queued':
            continue
        identity = (entry.get('ts'), entry.get('session_id'))
        if None in identity or identity in processed or identity in seen:
            continue
        seen.add(identity)
        entries.append(entry)
    return entries


def write_capture_log(ts, turn_estimate, summary, session_id, surface):
    today = datetime.now(timezone.utc).strftime('%Y%m%d')
    log_file = LOG_DIR / f'{today}.jsonl'
    try:
        LOG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(LOG_DIR, 0o700)
        entry = {
            'type': 'capture',
            'ts': ts,
            'turn_estimate': turn_estimate,
            'summary': summary,
            'session_id': session_id,
            'surface': surface,
            'user_id': None,
        }
        with open(log_file, 'a', encoding='ascii') as capture_log:
            capture_log.write(json.dumps(entry, separators=(',', ':')) + '\n')
            capture_log.flush()
        os.chmod(log_file, 0o600)
        return True
    except Exception:
        return False


def mark_processed(queue_target, orig_ts, session_id):
    marker = {
        'type': 'processed',
        'orig_ts': orig_ts,
        'session_id': session_id,
    }
    try:
        line = json.dumps(marker, separators=(',', ':')) + '\n'
        if hasattr(queue_target, 'write'):
            queue_target.seek(0, os.SEEK_END)
            queue_target.write(line)
            queue_target.flush()
            os.chmod(queue_target.name, 0o600)
        else:
            with open(queue_target, 'a', encoding='ascii') as queue_file:
                queue_file.write(line)
                queue_file.flush()
            os.chmod(queue_target, 0o600)
        return True
    except Exception:
        return False


def prune_old_logs(directory, max_days=7):
    try:
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=max_days)
        for candidate in directory.iterdir():
            if candidate.name.endswith('.jsonl') and len(candidate.stem) == 8:
                try:
                    file_date = datetime.strptime(candidate.stem, '%Y%m%d').date()
                    if file_date < cutoff:
                        candidate.unlink()
                except Exception:
                    pass
    except Exception:
        pass


def lock_queue_file(queue_file):
    lock = None
    try:
        queue_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(queue_file.parent, 0o700)
        lock = open(queue_file, 'a+', encoding='ascii')
        os.chmod(queue_file, 0o600)
        if sys.platform == 'win32':
            import portalocker
            portalocker.lock(lock, portalocker.LOCK_EX)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        return lock
    except Exception:
        if lock is not None:
            lock.close()
        return None


def unlock_queue_file(lock):
    if lock is None:
        return
    try:
        if sys.platform == 'win32':
            import portalocker
            portalocker.unlock(lock)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    lock.close()


def reserve_haiku_call(daily_limit):
    lock = lock_queue_file(STATE_LOCK_PATH)
    if lock is None:
        return False
    try:
        state = load_state()
        today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        if state.get('daily_date_utc') != today_utc:
            state['daily_haiku_calls'] = 0
            state['daily_date_utc'] = today_utc
        calls = int(state.get('daily_haiku_calls', 0))
        if calls >= daily_limit:
            save_state(state)
            return False
        state['daily_haiku_calls'] = calls + 1
        return save_state(state)
    finally:
        unlock_queue_file(lock)


def main():
    try:
        QUEUE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        LOG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(QUEUE_DIR, 0o700)
        os.chmod(LOG_DIR, 0o700)

        prune_old_logs(QUEUE_DIR, 7)
        prune_old_logs(LOG_DIR, 7)

        pro = is_pro_tier()
        can_call_haiku = pro and haiku_available()
        daily_limit = get_daily_limit()

        for queue_file in sorted(QUEUE_DIR.glob('*.jsonl')):
            lock = lock_queue_file(queue_file)
            if lock is None:
                continue
            try:
                for entry in read_queue_entries(lock):
                    excerpt = entry.get('excerpt', '')
                    session_id = entry.get('session_id', '')
                    surface = entry.get('surface', 'code')
                    ts = entry.get('ts', '')

                    summary = excerpt
                    if can_call_haiku and reserve_haiku_call(daily_limit):
                        summary = call_haiku(excerpt)

                    if write_capture_log(ts, 1, summary, session_id, surface):
                        mark_processed(lock, ts, session_id)
            finally:
                unlock_queue_file(lock)
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
