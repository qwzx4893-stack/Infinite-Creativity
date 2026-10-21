"""Shared request budgets and bounded, cancellation-aware blocking work.

No item data survives a request. Admission slots remain owned by the worker
until it actually exits, including when its caller has already cancelled.
"""
import asyncio
import contextvars
import threading
import time
from dataclasses import dataclass, field


class RequestCancelled(BaseException):
    """Bypasses provider error-to-empty-result handlers during cancellation."""


@dataclass
class RequestScope:
    seconds: float = 120
    max_requests: int = 256
    max_bytes: int = 640 * 1024 * 1024
    cancelled: threading.Event = field(default_factory=threading.Event)
    started: float = field(default_factory=time.monotonic)
    requests: int = 0
    received_bytes: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def check(self):
        if self.cancelled.is_set():
            raise RequestCancelled('Request cancelled')
        if time.monotonic() - self.started > self.seconds:
            raise ValueError('Request deadline exceeded; narrow the source or selection')

    def account(self, requests=0, received_bytes=0):
        self.check()
        with self.lock:
            self.requests += requests
            self.received_bytes += received_bytes
            if self.requests > self.max_requests:
                raise ValueError('Aggregate request HTTP budget exceeded')
            if self.received_bytes > self.max_bytes:
                raise ValueError('Aggregate request transfer budget exceeded')


CURRENT = contextvars.ContextVar('infinite_creativity_request', default=None)


def checkpoint(requests=0, received_bytes=0):
    scope = CURRENT.get()
    if scope is not None:
        scope.account(requests, received_bytes)


def context_map(pool, function, values):
    """Executor.map with the caller's cancellation/budgets in every child."""
    futures = []
    for value in values:
        checkpoint()
        context = contextvars.copy_context()
        futures.append(pool.submit(context.run, function, value))
    for future in futures:
        while True:
            checkpoint()
            try:
                yield future.result(timeout=.05)
                break
            except TimeoutError:
                if future.done():
                    raise


class Admission:
    def __init__(self, active=4, heavy=2, pending=12):
        self.capacity = active
        self.heavy_capacity = heavy
        self.pending_capacity = pending
        self.slots = threading.BoundedSemaphore(active)
        self.heavy_slots = threading.BoundedSemaphore(heavy)
        self.lock = threading.Lock()
        self.pending = self.active = self.heavy = 0

    def reserve(self):
        with self.lock:
            if self.pending >= self.pending_capacity:
                raise ValueError('Server capacity busy; retry after current requests finish')
            self.pending += 1

    def metrics(self):
        with self.lock:
            return dict(active=self.active, heavy=self.heavy,
                        queued=self.pending - self.active,
                        max_active=self.capacity, max_heavy=self.heavy_capacity,
                        max_pending=self.pending_capacity)

    def execute(self, scope, function, heavy):
        slot = heavy_slot = entered = False
        token = CURRENT.set(scope)
        try:
            # Acquire the scarce heavy slot first so heavy waiters cannot
            # occupy every ordinary slot and starve lightweight navigation.
            if heavy:
                while not heavy_slot:
                    scope.check()
                    heavy_slot = self.heavy_slots.acquire(timeout=.05)
            while not slot:
                scope.check()
                slot = self.slots.acquire(timeout=.05)
            scope.check()
            with self.lock:
                self.active += 1
                self.heavy += int(heavy)
                entered = True
            result = function()
            scope.check()
            return result
        finally:
            CURRENT.reset(token)
            with self.lock:
                if entered:
                    self.active -= 1
                    self.heavy -= int(heavy)
                self.pending -= 1
            if slot:
                self.slots.release()
            if heavy_slot:
                self.heavy_slots.release()


GATE = Admission()


def _observe(future):
    try:
        future.exception()
    except BaseException:
        pass


async def run_blocking(function, *, heavy=False, seconds=None):
    GATE.reserve()
    scope = RequestScope(seconds=seconds or (330 if heavy else 120))
    worker = asyncio.create_task(asyncio.to_thread(GATE.execute, scope, function, heavy))
    worker.add_done_callback(_observe)
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        scope.cancelled.set()
        # AnyIO's MCP cancellation may cancel each subsequent await. Shield
        # cleanup briefly; a stuck native worker still owns its admission slot.
        import anyio
        with anyio.move_on_after(2, shield=True):
            try:
                await asyncio.shield(worker)
            except (RequestCancelled, asyncio.CancelledError):
                pass
        raise


def runtime_status():
    return {'admission': GATE.metrics(),
            'request_limits': {'seconds': 120, 'selected_seconds': 330,
                               'http_requests': 256, 'decoded_bytes': 640 * 1024 * 1024},
            'cancellation': 'Cooperative transport/parser checkpoints; isolated media workers have process deadlines.'}
