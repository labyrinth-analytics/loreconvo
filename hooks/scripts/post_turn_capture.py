#!/usr/bin/env python3
# -*- coding: ascii -*-

import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path


STATE_PATH = Path.home() / '.loreconvo' / 'capture_state.json'
STATE_LOCK_PATH = Path.home() / '.loreconvo' / '.capture_state.lock'
QUEUE_DIR = Path.home() / '.loreconvo' / 'capture_queue'
MAX_DAYS_OLD = 7


def load_state():
    try:
        with open(STATE_PATH, 'r', encoding='ascii') as state_file:
            return json.load(state_file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        now_utc = datetime.now(timezone.utc)
        return {
            'session_id': str(uuid.uuid4()),
            'tool_call_count': 0,
            'daily_haiku_calls': 0,
            'daily_date_utc': now_utc.strftime('%Y-%m-%d'),
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


def _lock_file(path):
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        lock = open(path, 'a+', encoding='ascii')
        os.chmod(path, 0o600)
        if sys.platform == 'win32':
            import portalocker
            portalocker.lock(lock, portalocker.LOCK_EX)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        return lock
    except Exception:
        try:
            lock.close()
        except Exception:
            pass
        return None


def _unlock_file(lock):
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


def _read_hook_input():
    try:
        stdin_data = sys.stdin.read()
    except Exception:
        return {}, ''
    if not stdin_data:
        return {}, ''
    try:
        payload = json.loads(stdin_data)
    except json.JSONDecodeError:
        return {}, stdin_data
    if not isinstance(payload, dict):
        return {}, ''
    return payload, ''


def read_transcript(hook_input=None, raw_stdin=''):
    hook_input = hook_input or {}
    transcript_path = (
        os.environ.get('CLAUDE_TRANSCRIPT_PATH')
        or hook_input.get('transcript_path')
    )
    if transcript_path:
        try:
            with open(transcript_path, 'r', encoding='ascii', errors='replace') as transcript:
                content = transcript.read()
                return content[-500:] if len(content) > 500 else content
        except Exception:
            return ''
    return raw_stdin[-500:] if len(raw_stdin) > 500 else raw_stdin


def _advance_capture_state(requested_session_id):
    lock = _lock_file(STATE_LOCK_PATH)
    if lock is None:
        return None, None
    try:
        state = load_state()
        session_id = requested_session_id or state.get('session_id') or str(uuid.uuid4())
        if state.get('session_id') != session_id:
            state['session_id'] = session_id
            state['tool_call_count'] = 0
            state['worker_not_found_warned'] = False
        state['tool_call_count'] = int(state.get('tool_call_count', 0)) + 1
        if not save_state(state):
            return None, None
        return state, session_id
    finally:
        _unlock_file(lock)


def write_queue_entry(entry_dict):
    utc_date = datetime.now(timezone.utc).strftime('%Y%m%d')
    queue_file = QUEUE_DIR / f'{utc_date}.jsonl'
    try:
        QUEUE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(QUEUE_DIR, 0o700)
        line = json.dumps(entry_dict, separators=(',', ':')) + '\n'
        with open(queue_file, 'a', encoding='ascii') as queue:
            if sys.platform == 'win32':
                import portalocker
                portalocker.lock(queue, portalocker.LOCK_EX)
            else:
                import fcntl
                fcntl.flock(queue.fileno(), fcntl.LOCK_EX)
            try:
                queue.write(line)
                queue.flush()
                os.chmod(queue_file, 0o600)
            finally:
                if sys.platform == 'win32':
                    portalocker.unlock(queue)
                else:
                    fcntl.flock(queue.fileno(), fcntl.LOCK_UN)
        return True
    except Exception:
        return False


def prune_old_queues():
    try:
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=MAX_DAYS_OLD)
        for queue_file in QUEUE_DIR.iterdir():
            if queue_file.name.endswith('.jsonl') and len(queue_file.stem) == 8:
                try:
                    file_date = datetime.strptime(queue_file.stem, '%Y%m%d').date()
                    if file_date < cutoff:
                        queue_file.unlink()
                except Exception:
                    pass
    except Exception:
        pass


def _mark_worker_missing(session_id):
    lock = _lock_file(STATE_LOCK_PATH)
    if lock is None:
        return False
    try:
        state = load_state()
        if state.get('session_id') != session_id:
            return False
        if state.get('worker_not_found_warned', False):
            return False
        state['worker_not_found_warned'] = True
        return save_state(state)
    finally:
        _unlock_file(lock)


def spawn_worker(session_id):
    worker_path = Path(__file__).resolve().with_name('capture_worker.py')
    try:
        if not worker_path.is_file():
            raise FileNotFoundError(str(worker_path))
        subprocess.Popen(
            [sys.executable, str(worker_path)],
            start_new_session=True,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except FileNotFoundError:
        if _mark_worker_missing(session_id):
            sys.stderr.write(
                '[LORECONVO-WARN] bundled capture_worker.py not found -- '
                'captures are queued but will not be summarized\n')
            sys.stderr.flush()
        return False
    except Exception:
        return False


def main():
    if os.environ.get('LORECONVO_POST_TURN_CAPTURE', '') != '1':
        return 0

    if sys.platform == 'win32':
        try:
            import portalocker  # noqa: F401
        except ImportError:
            return 0

    try:
        hook_input, raw_stdin = _read_hook_input()
        requested_session_id = (
            os.environ.get('LORECONVO_AGENT_RUN_SESSION_ID')
            or hook_input.get('session_id')
        )
        state, session_id = _advance_capture_state(requested_session_id)
        if state is None:
            return 0

        try:
            interval = int(os.environ.get('LORECONVO_TURN_CAPTURE_INTERVAL', '10'))
        except ValueError:
            return 0
        if interval <= 0 or state['tool_call_count'] % interval != 0:
            return 0

        excerpt = read_transcript(hook_input, raw_stdin)
        if not excerpt:
            return 0

        entry = {
            'type': 'queued',
            'ts': datetime.now(timezone.utc).isoformat(),
            'excerpt': excerpt,
            'session_id': session_id,
            'surface': os.environ.get('LORECONVO_SURFACE', 'code'),
        }

        if write_queue_entry(entry):
            prune_old_queues()
            spawn_worker(session_id)
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
