"""Shared-account rate control and redacted retry errors for new experiments."""
import hashlib
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from .llm import ChatCompletionsClient,LLMError

_LOCK=threading.Lock()

def safe_error(message,key=''):
    if key:message=message.replace(key,'[REDACTED]')
    return re.sub(r'(?i)\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b',
                  lambda m:'request_sha256_'+hashlib.sha256(m.group().encode()).hexdigest(),message)

def reserve(key,rpm):
    interval=60/max(1,min(float(rpm),50))
    path=Path(tempfile.gettempdir())/('chronofin-rate-'+hashlib.sha256(key.encode()).hexdigest()[:16]+'.txt')
    with _LOCK:
        with path.open('a+') as f:
            try:
                import fcntl
                fcntl.flock(f.fileno(),fcntl.LOCK_EX)
            except ImportError:fcntl=None
            f.seek(0)
            try:next_at=float(f.read() or 0)
            except ValueError:next_at=0
            now=time.time();slot=max(now,next_at);f.seek(0);f.truncate();f.write(str(slot+interval));f.flush()
            if fcntl:fcntl.flock(f.fileno(),fcntl.LOCK_UN)
    if slot>now:time.sleep(slot-now)

class RateLimitedClient(ChatCompletionsClient):
    def __init__(self,config,max_attempts=3,rpm=None):
        super().__init__(config,max_attempts=1)
        self.outer_attempts=max_attempts
        self.rpm=float(rpm or os.environ.get('HY3_RPM','40'))
    def complete_json(self,system,user):
        started=time.monotonic();last=None
        for attempt in range(1,self.outer_attempts+1):
            reserve(self.config.api_key,self.rpm)
            try:
                result,trace=super().complete_json(system,user)
                trace.attempts=attempt;trace.latency_seconds=time.monotonic()-started
                return result,trace
            except LLMError as e:
                last=safe_error(str(e),self.config.api_key)
                if 'HTTP 402' in last or 'HTTP 401' in last:break
                if attempt<self.outer_attempts:time.sleep(61 if 'HTTP 429' in last else min(8,2**attempt))
        raise LLMError(last or 'Hy3 call failed')
