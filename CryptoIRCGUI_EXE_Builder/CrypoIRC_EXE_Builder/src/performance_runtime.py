"""Bounded background executor for responsive Tk applications.

Important: every submitted call must have its own network timeouts; Python cannot
forcibly interrupt a hanging native/RPC call. No keys, payloads, exceptions or
argument values are stored in diagnostic statistics.
"""
from __future__ import annotations
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from queue import Queue, Empty
import threading
import time


class QueueSaturated(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeStats:
    running: int
    queued: int
    completed: int
    failed: int
    rejected: int
    busy_keys: int
    p95_ms: float
    peak_active: int
    financial_running: int = 0
    financial_queued: int = 0


class DesktopExecutor:
    """Tk main-thread pump + bounded worker execution; keyed single-flight jobs.

    All user callbacks execute in the Tk main thread via poll(), never workers.
    The worker thread never calls root.after()/Tcl. The Tk main thread must
    create this object, and call .start() in the same thread.
    """
    def __init__(self, root, *, workers=4, queued=32, interval_ms=75):
        if workers < 1 or queued < 1:raise ValueError('Executor capacity must be positive')
        self.root=root
        self.workers=workers
        self.interval_ms=interval_ms
        self._pool=ThreadPoolExecutor(max_workers=workers, thread_name_prefix='Nocturne-io')
        # Financial jobs have a reserved pool to avoid read/chat starvation.
        self._financial_pool=ThreadPoolExecutor(max_workers=2, thread_name_prefix='Nocturne-finance')
        self._slots=threading.BoundedSemaphore(workers+queued)
        self._financial_slots=threading.BoundedSemaphore(10)
        self._lock=threading.Lock()
        self._keyed=set()
        self._ui=Queue()  # max outstanding results bounded by slots
        self._running=0
        self._queued=0
        self._financial_running=0
        self._financial_queued=0
        self._peak=0
        self._completed=0
        self._failed=0
        self._rejected=0
        self._samples=deque(maxlen=400)
        self._closed=False
        self._timer=None

    def start(self):
        if self._closed:raise RuntimeError('Executor already closed')
        if self._timer is None:self._timer=self.root.after(self.interval_ms,self._tick)

    def submit(self, work, success, error=None, *, key=None, lane='io'):
        """Schedule work without blocking the GUI; return False on duplicate key.

        On failure, invoke error(error_type_name) if provided, never transmit
        raw exception text/arguments to the UI or diagnostics.
        """
        if lane not in ('io','financial'):raise ValueError('Unknown execution lane')
        slots=self._financial_slots if lane=='financial' else self._slots
        pool=self._financial_pool if lane=='financial' else self._pool
        with self._lock:
            if self._closed:raise RuntimeError('Executor closed')
            if key is not None and key in self._keyed:return False
            if not slots.acquire(blocking=False):
                self._rejected+=1
                raise QueueSaturated('Background queue busy; retry shortly')
            if key is not None:self._keyed.add(key)
            if lane=='financial':self._financial_queued+=1
            else:self._queued+=1
        submitted_at=time.monotonic()

        def invoke():
            with self._lock:
                if lane=='financial':
                    self._financial_queued-=1
                    self._financial_running+=1
                else:
                    self._queued-=1
                    self._running+=1
                self._peak=max(self._peak,self._running+self._financial_running)
            outcome=None
            try:
                value=work()
                ok=True
            except Exception as exc:
                value=type(exc).__name__  # never copy exception contents/secrets
                ok=False
            finally:
                elapsed_ms=(time.monotonic()-submitted_at)*1000
                with self._lock:
                    if lane=='financial':self._financial_running-=1
                    else:self._running-=1
                    self._completed+=1
                    if not ok:self._failed+=1
                    self._samples.append(elapsed_ms)
            self._ui.put((ok,value,success,error,key,slots))

        try:pool.submit(invoke)
        except BaseException:
            with self._lock:
                if lane=='financial':self._financial_queued-=1
                else:self._queued-=1
                if key is not None:self._keyed.discard(key)
            slots.release()
            raise
        return True

    def poll(self, max_callbacks=64):
        """Drain a bounded number of completions from the GUI thread."""
        count=0
        while count<max_callbacks:
            try:ok,value,success,error,key,slots=self._ui.get_nowait()
            except Empty:break
            count+=1
            with self._lock:
                if key is not None:self._keyed.discard(key)
            slots.release()
            if self._closed:continue
            if ok:
                if success is not None:success(value)
            elif error is not None:error(value)
        return count

    def _tick(self):
        self._timer=None
        if self._closed:return
        try:self.poll()
        finally:
            if not self._closed:self._timer=self.root.after(self.interval_ms,self._tick)

    def stats(self):
        with self._lock:
            ordered=sorted(self._samples)
            p95=ordered[max(0,int(.95*(len(ordered)-1)))] if ordered else 0.0
            return RuntimeStats(self._running,self._queued,self._completed,self._failed,
                                self._rejected,len(self._keyed),round(p95,1),self._peak,
                                self._financial_running,self._financial_queued)

    def close(self):
        with self._lock:self._closed=True
        if self._timer is not None:
            try:self.root.after_cancel(self._timer)
            except (RuntimeError, ValueError):pass
            self._timer=None
        self._pool.shutdown(wait=False,cancel_futures=True)
        self._financial_pool.shutdown(wait=False,cancel_futures=True)
