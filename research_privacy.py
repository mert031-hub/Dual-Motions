"""Local research audit events and conservative artifact minimization."""
import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

_LOCK = threading.RLock()
DATA_DIR = Path(os.getenv('RESEARCH_DATA_DIR', str(Path(__file__).resolve().parent / 'runtime')))
_TEXT_KEYS = {'user_message', 'final_output', 'rationale', 'judge_rationale', 'reason', 'notes',
              'matched_keyword', 'evidence', 'quote', 'prompt', 'flaws_x', 'flaws_y', 'title',
              'policy_draft', 'critic_reason', 'critic_revision_notes', 'risky_spans'}


def minimize(value, persist_text=False):
    if isinstance(value, dict):
        return {k: ('' if k in _TEXT_KEYS and not persist_text else
                    ('[error]' if v else '') if k in {'error', 'judge_error'} and not persist_text else
                    [] if k == 'judge_errors' and not persist_text else minimize(v, persist_text))
                for k, v in value.items()}
    if isinstance(value, list):
        return [minimize(v, persist_text) for v in value]
    return value


def mask_identifiers(text):
    """Best effort only: cannot reliably remove names, addresses or contextual identifiers."""
    text = re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', '[EMAIL]', text)
    text = re.sub(r'(?<!\w)\+?\d[\d ()-]{8,}\d(?!\w)', '[NUMBER]', text)
    return text


class AuditLog:
    allowed_fields = {'system', 'model', 'needs_human_review', 'llm_calls', 'latency_s', 'triage_tier', 'error_type'}

    def __init__(self, directory=None, include_text=False):
        self.directory = Path(directory) if directory is not None else DATA_DIR / 'audit'
        self.include_text = include_text

    def record(self, session_id, event, text=None, **metadata):
        if event not in {'turn', 'session_deleted', 'benchmark'}:
            raise ValueError('Unknown audit event')
        if not re.fullmatch(r'[a-f0-9]{32}', session_id):
            raise ValueError('Session id must be an opaque UUID hex')
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        now = datetime.now(timezone.utc)
        payload = {'time': now.isoformat(), 'session_id': session_id, 'event': event}
        payload.update({k: v for k, v in metadata.items() if k in self.allowed_fields})
        if self.include_text and text:
            payload['text'] = mask_identifiers(text)
        line = (json.dumps(payload, ensure_ascii=False, allow_nan=False) + '\n').encode()
        with _LOCK:
            fd = os.open(self.directory / f'audit-{now.date().isoformat()}.jsonl', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, 'ab') as handle:
                handle.write(line)

    def purge(self, retention_days):
        if retention_days < 0:
            raise ValueError('Retention days cannot be negative')
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        deleted = 0
        with _LOCK:
            for path in self.directory.glob('audit-*.jsonl'):
                if not path.is_symlink() and datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff:
                    path.unlink()
                    deleted += 1
        return deleted

    def delete_session(self, session_id):
        if not re.fullmatch(r'[a-f0-9]{32}', session_id):
            raise ValueError('Invalid session id')
        from storage import write_json_lines
        with _LOCK:
            for path in self.directory.glob('audit-*.jsonl'):
                if path.is_symlink():
                    continue
                entries = [json.loads(line) for line in path.read_text().splitlines() if line]
                write_json_lines(path, [e for e in entries if e.get('session_id') != session_id])
