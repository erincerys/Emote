import collections
import ctypes
import datetime
import functools
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback

from gi.repository import Gdk, GLib

from emote import user_data

path = os.path.join(user_data.DATA_DIR, "diag.log")
MAX_BYTES = 1_000_000
SLOW_MS = 1000
MISSING_AFTER = 5.0
HEARTBEAT = 0.25
STALL_AFTER = 1.0
WATCH_INTERVAL = 0.1
GDB_AFTER = 3.0
GDB_INTERVAL = 600
GDB_TIMEOUT = 20
GDB_MAX_CHARS = 64_000
PR_SET_PTRACER = 0x59616D61

STAGES = (
    "key",
    "dispatch",
    "activate",
    "prepared",
    "surface",
    "mapped",
    "presented",
    "painted",
    "active",
)
CLOSE_STAGES = ("key", "dispatch")

_write_lock = threading.Lock()
renderer_name = None


def disable():
    global path
    path = None


def format_line(message, now=None):
    stamp = (now or datetime.datetime.now()).isoformat(timespec="milliseconds")
    first, *rest = str(message).split("\n")
    return "".join([f"{stamp} {first}\n", *(f"{stamp}   {line}\n" for line in rest)])


def log(message):
    target = path
    if target is None:
        return
    try:
        line = format_line(message)
        with _write_lock:
            try:
                if os.path.getsize(target) > MAX_BYTES:
                    os.replace(target, target + ".1")
            except OSError:
                pass
            with open(target, "a", encoding="utf-8") as log_file:
                log_file.write(line)
    except Exception:
        pass


def guarded(function):
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception:
            log(f"diag {function.__name__} failed\n{traceback.format_exc().rstrip()}")

    return wrapper


def hook(function):
    guarded_function = guarded(function)

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        if path is not None:
            return guarded_function(*args, **kwargs)

    return wrapper


def ms(seconds):
    return round(seconds * 1000)


def _read_proc(name):
    try:
        with open(name, encoding="ascii", errors="replace") as proc_file:
            return proc_file.read().strip()
    except OSError as error:
        return f"<{error.strerror}>"


def proc_report():
    main = threading.main_thread().native_id
    lines = [
        f"main thread {main} wchan {_read_proc(f'/proc/self/task/{main}/wchan')}"
        f" syscall {_read_proc(f'/proc/self/task/{main}/syscall')}"
    ]
    groups = {}
    for task in sorted(os.listdir("/proc/self/task"), key=int):
        stat = _read_proc(f"/proc/self/task/{task}/stat")
        # comm is parenthesised and may contain spaces; the state follows it.
        close = stat.rfind(")")
        comm = re.sub(r"-?\d+$", "", stat[stat.find("(") + 1 : close])
        state = stat[close + 2 : close + 3]
        wchan = _read_proc(f"/proc/self/task/{task}/wchan")
        groups.setdefault((comm, state, wchan), []).append(task)
    for (comm, state, wchan), tasks in groups.items():
        lines.append(
            f"threads {comm} x{len(tasks)} state {state} wchan {wchan}"
            f" (tid {tasks[0]})"
        )
    return lines


def compact_gdb(text):
    blocks = {}
    for block in text.split("\n\n"):
        header, _, body = block.partition("\n")
        if header.startswith("Thread "):
            blocks.setdefault(body, []).append(header)
            continue
        kept = [line for line in block.splitlines() if not line.startswith("[New LWP")]
        if kept:
            blocks.setdefault("\n".join(kept), [])
    parts = []
    for body, headers in blocks.items():
        if not headers:
            parts.append(body)
            continue
        more = f" and {len(headers) - 1} more" if len(headers) > 1 else ""
        parts.append(f"{headers[0]}{more}\n{body}")
    return "\n\n".join(parts)


def main_stack():
    frame = sys._current_frames().get(threading.main_thread().ident)
    if frame is None:
        return ("<no Python frame>",)
    summary = traceback.StackSummary.extract(
        traceback.walk_stack(frame), limit=12, lookup_lines=False
    )
    return tuple(
        f"{os.path.basename(entry.filename)}:{entry.lineno} {entry.name}"
        for entry in reversed(summary)
    )


def x_lag_ms(event_time, now=None):
    # Xorg stamps events with CLOCK_MONOTONIC milliseconds truncated to 32 bits,
    # the same clock as time.monotonic(), so the difference is delivery delay.
    now_ms = int((time.monotonic() if now is None else now) * 1000) & 0xFFFFFFFF
    lag = (now_ms - event_time + 2**31) % 2**32 - 2**31
    return lag if abs(lag) < 600_000 else None


class _Open:
    def __init__(self, stage, at, info):
        self.start = stage
        self.t0 = at
        self.times = {stage: at}
        self.info = info
        self.kind = "open"

    def expected(self):
        stages = CLOSE_STAGES if self.kind == "close" else STAGES
        return stages[stages.index(self.start) :] if self.start in stages else ()

    def complete(self):
        return all(stage in self.times for stage in self.expected())


class OpenTimeline:
    def __init__(
        self, clock=time.monotonic, write=log, report=proc_report, on_pending=None
    ):
        self.clock = clock
        self.write = write
        self.report = report
        self.on_pending = on_pending
        self.lock = threading.Lock()
        self.current = None

    def begin(self, stage, **info):
        with self.lock:
            previous, self.current = self.current, _Open(stage, self.clock(), info)
            record = self.current
        if previous is not None:
            self.finish(previous, "superseded")
        if self.on_pending:
            self.on_pending(True)
        return record

    def mark(self, stage, record=None, **info):
        now = self.clock()
        with self.lock:
            current = self.current
            if record is not None and record is not current:
                return
        if current is None:
            if stage not in ("dispatch", "activate"):
                return
            current = self.begin(stage)
        with self.lock:
            if current is not self.current:
                return
            if stage == "dispatch":
                current.kind = info.pop("action", "open")
            current.times.setdefault(stage, now)
            current.info.update(info)
            done = current.complete()
            if done:
                self.current = None
        if done:
            self.finish(current)

    def check_overdue(self):
        with self.lock:
            record = self.current
            if record is None or self.clock() - record.t0 < MISSING_AFTER:
                return
            self.current = None
        self.finish(record, "overdue")

    def finish(self, record, reason=None):
        if self.on_pending and reason != "superseded":
            self.on_pending(False)
        expected = record.expected()
        missing = [stage for stage in expected if stage not in record.times]
        offsets = [
            (
                f"{stage} {ms(record.times[stage] - record.t0)}"
                if stage in record.times
                else f"{stage} -"
            )
            for stage in expected[1:]
        ]
        line = f"{record.kind} {record.start}→{' '.join(offsets)} ms"
        if record.info.get("x_lag") is not None:
            line += f"; x_lag {record.info['x_lag']} ms"
        end_stage = next(
            (s for s in ("active", "painted") if s in record.times),
            max(record.times, key=record.times.get),
        )
        total = ms(record.times[end_stage] - record.t0)
        if not missing and total <= SLOW_MS:
            self.write(line)
            return
        details = [line]
        if missing:
            details.append(
                f"incomplete ({reason or 'finished'}) after"
                f" {ms(self.clock() - record.t0)} ms; missing {', '.join(missing)}"
            )
        if total > SLOW_MS:
            details.append(f"slow: {total} ms to {end_stage} (limit {SLOW_MS})")
        steps = sorted(record.times, key=record.times.get)
        if len(steps) > 1:
            gap, before, after = max(
                (record.times[b] - record.times[a], a, b)
                for a, b in zip(steps, steps[1:])
            )
            details.append(f"slowest step {before}→{after} {ms(gap)} ms")
        if record.info.get("loop") is not None:
            details.append(f"listener loop {record.info['loop']} ms before key read")
        details.append(f"renderer {renderer_name or 'unknown'}")
        details.extend(self.report())
        self.write("\n".join(details))


def capture_native_stack(write=log):
    gdb = shutil.which("gdb")
    if gdb is None:
        write("native stack skipped: gdb not on PATH")
        return
    started = time.monotonic()
    command = (
        f"read _ && exec {gdb} -p {os.getpid()} -batch -nx"
        ' -iex "set debuginfod enabled off" -ex "thread apply all bt 30"'
    )
    child = subprocess.Popen(
        ["sh", "-c", command],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [ctypes.c_int] + [ctypes.c_ulong] * 4
    try:
        # Yama ptrace_scope 1 only lets ancestors attach. Name this child, which
        # is still waiting on stdin, as the one process allowed to trace us.
        if libc.prctl(PR_SET_PTRACER, child.pid, 0, 0, 0) != 0:
            write(f"PR_SET_PTRACER failed: {os.strerror(ctypes.get_errno())}")
        try:
            output, _ = child.communicate(b"\n", timeout=GDB_TIMEOUT)
            note = ""
        except subprocess.TimeoutExpired:
            child.kill()
            output, _ = child.communicate()
            note = f" (killed after {GDB_TIMEOUT} s)"
    finally:
        libc.prctl(PR_SET_PTRACER, 0, 0, 0, 0)
    text = compact_gdb(output.decode("utf-8", "replace").rstrip())[:GDB_MAX_CHARS]
    write(
        f"native stack, gdb exit {child.returncode}{note},"
        f" {ms(time.monotonic() - started)} ms\n{text}"
    )


class _Stall:
    def __init__(self, start, report):
        self.start = start
        self.report = report
        self.stacks = collections.Counter()
        self.native_requested = False

    def summary(self, recovered):
        lines = [
            f"main loop stall {ms(recovered - self.start)} ms,"
            f" {sum(self.stacks.values())} stack samples"
        ]
        lines.extend(self.report)
        for stack, count in self.stacks.most_common(5):
            lines.append(f"[{count}x]")
            lines.extend(f"  {frame}" for frame in stack)
        return "\n".join(lines)


class StallWatchdog:
    def __init__(self, timeline, write=log, clock=time.monotonic):
        self.timeline = timeline
        self.write = write
        self.clock = clock
        self.lock = threading.Lock()
        self.holds = set()
        self.last_beat = 0.0
        self.beat_source = None
        self.thread = None
        self.last_native = None

    def hold(self, reason):
        with self.lock:
            self.holds.add(reason)
            if self.beat_source is None:
                self.last_beat = self.clock()
                self.beat_source = GLib.timeout_add(ms(HEARTBEAT), self.beat)
            if self.thread is None:
                self.thread = threading.Thread(
                    target=self.watch, name="emote-diag", daemon=True
                )
                self.thread.start()

    def release(self, reason):
        with self.lock:
            self.holds.discard(reason)

    def beat(self):
        with self.lock:
            self.last_beat = self.clock()
            if self.holds:
                return GLib.SOURCE_CONTINUE
            self.beat_source = None
            return GLib.SOURCE_REMOVE

    def watch(self):
        stall = None
        while True:
            time.sleep(WATCH_INTERVAL)
            with self.lock:
                if not self.holds and stall is None:
                    self.thread = None
                    return
                last = self.last_beat
            try:
                self.timeline.check_overdue()
                stall = self.check(stall, last)
            except Exception:
                self.write(f"diag watchdog failed\n{traceback.format_exc().rstrip()}")
                stall = None

    def check(self, stall, last):
        now = self.clock()
        if now - last - HEARTBEAT > STALL_AFTER:
            if stall is None:
                stall = _Stall(last + HEARTBEAT, proc_report())
            stall.stacks[main_stack()] += 1
            if now - stall.start > GDB_AFTER and not stall.native_requested:
                stall.native_requested = True
                self.request_native_stack(now)
            return stall
        if stall is not None:
            self.write(stall.summary(last))
        return None

    def request_native_stack(self, now):
        if self.last_native is not None and now - self.last_native < GDB_INTERVAL:
            self.write("native stack skipped: one capture per 10 minutes")
            return
        self.last_native = now
        threading.Thread(
            target=guarded(capture_native_stack),
            args=(self.write,),
            name="emote-diag-gdb",
            daemon=True,
        ).start()


class PaintWatch:
    def __init__(self):
        self.clock = None
        self.handler = None

    def cancel(self):
        if self.handler is not None:
            self.clock.disconnect(self.handler)
        self.clock = None
        self.handler = None

    def watch(self, widget, callback):
        self.cancel()
        clock = widget.get_frame_clock()
        if clock is None:
            return

        def painted(_clock):
            self.cancel()
            guarded(callback)(time.monotonic())

        self.clock = clock
        self.handler = clock.connect("after-paint", painted)


def _open_pending(pending):
    if pending:
        watchdog.hold("open")
    else:
        watchdog.release("open")


opens = OpenTimeline(on_pending=_open_pending)
watchdog = StallWatchdog(opens)
open_paint = PaintWatch()
search_paint = PaintWatch()


@hook
def daemon_started():
    display = Gdk.Display.get_default()
    log(f"start pid {os.getpid()} display {display.__gtype__.name}")


@hook
def listener_starved(seconds):
    log(f"hotkey listener starved: one 40 ms wait took {ms(seconds)} ms")


@hook
def key_pressed(event_time, loop_seconds):
    opens.begin("key", x_lag=x_lag_ms(event_time), loop=ms(loop_seconds))


@hook
def mark(stage, **info):
    opens.mark(stage, **info)


@hook
def presented(window):
    opens.mark("presented")
    record = opens.current
    if record is not None:
        open_paint.watch(window, lambda _at: opens.mark("painted", record=record))


@hook
def picker_mapped(window):
    global renderer_name
    opens.mark("mapped")
    renderer = window.get_renderer()
    renderer_name = renderer.__gtype__.name if renderer is not None else None
    watchdog.hold("visible")


@hook
def watch_surface(surface):
    surface.connect("notify::mapped", _surface_mapped)


@hook
def _surface_mapped(surface, _property):
    if surface.get_mapped():
        opens.mark("surface")


@hook
def picker_hidden():
    open_paint.cancel()
    search_paint.cancel()
    watchdog.release("visible")


@hook
def search_applied(widget, query, results, keyed_at, started):
    finished = time.monotonic()
    length = len(query.strip())
    log(
        f"search len {length} results {'-' if results is None else results}"
        f" apply {ms(finished - started)} ms"
    )
    if keyed_at is None:
        return

    def painted(at):
        if ms(at - keyed_at) > SLOW_MS:
            log(
                f"search slow: len {length} keystroke→apply {ms(started - keyed_at)}"
                f" apply {ms(finished - started)} painted {ms(at - keyed_at)} ms"
                f" (limit {SLOW_MS}); renderer {renderer_name or 'unknown'}"
            )

    search_paint.watch(widget, painted)
