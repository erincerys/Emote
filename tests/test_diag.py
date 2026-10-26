import datetime
import os
import tempfile
from unittest import TestCase
from unittest.mock import Mock, patch

from emote import diag


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def at(self, offset_ms):
        self.now = 100.0 + offset_ms / 1000


class DiagLogTests(TestCase):
    def test_every_line_starts_with_a_millisecond_timestamp(self):
        now = datetime.datetime(2026, 10, 26, 1, 2, 3, 45000)

        self.assertEqual(
            diag.format_line("open\nslow", now),
            "2026-10-26T01:02:03.045 open\n2026-10-26T01:02:03.045   slow\n",
        )

    def test_log_rotates_after_one_megabyte(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "diag.log")
            with open(target, "w") as log_file:
                log_file.write("x" * (diag.MAX_BYTES + 1))

            with patch("emote.diag.path", target):
                diag.log("after")

            self.assertEqual(os.path.getsize(target + ".1"), diag.MAX_BYTES + 1)
            with open(target) as log_file:
                self.assertTrue(log_file.read().endswith(" after\n"))

    def test_log_swallows_write_errors(self):
        with patch("emote.diag.path", "/nonexistent/dir/diag.log"):
            diag.log("lost")

    def test_hooks_do_nothing_when_disabled(self):
        with patch("emote.diag.path", None), patch.object(diag.opens, "mark") as mark:
            diag.mark("active")
        mark.assert_not_called()

    def test_x_lag_uses_wrapping_server_milliseconds(self):
        self.assertEqual(diag.x_lag_ms(2**32 - 2, now=0.003), 5)
        self.assertIsNone(diag.x_lag_ms(123, now=5000.0))


class OpenTimelineTests(TestCase):
    def make_timeline(self):
        self.clock = FakeClock()
        self.lines = []
        self.pending = []
        return diag.OpenTimeline(
            clock=self.clock,
            write=self.lines.append,
            report=lambda: ["main thread 1 wchan do_poll syscall 7"],
            on_pending=self.pending.append,
        )

    def run_open(self, timeline, offsets):
        self.clock.at(0)
        timeline.begin("key", x_lag=1, loop=40)
        for stage, offset in offsets:
            self.clock.at(offset)
            info = {"action": "open"} if stage == "dispatch" else {}
            timeline.mark(stage, **info)

    def test_fast_open_logs_one_quiet_line(self):
        timeline = self.make_timeline()

        self.run_open(
            timeline,
            [
                ("dispatch", 2),
                ("activate", 3),
                ("prepared", 15),
                ("surface", 16),
                ("mapped", 17),
                ("presented", 18),
                ("painted", 52),
                ("active", 61),
            ],
        )

        self.assertEqual(
            self.lines,
            [
                "open key→dispatch 2 activate 3 prepared 15 surface 16 mapped 17"
                " presented 18 painted 52 active 61 ms; x_lag 1 ms"
            ],
        )
        self.assertEqual(self.pending, [True, False])
        self.assertIsNone(timeline.current)

    def test_slow_open_names_the_slow_step(self):
        timeline = self.make_timeline()

        self.run_open(
            timeline,
            [
                ("dispatch", 2),
                ("activate", 3),
                ("prepared", 15),
                ("presented", 16),
                ("mapped", 1400),
                ("surface", 1410),
                ("painted", 1450),
                ("active", 1500),
            ],
        )

        [block] = self.lines
        self.assertIn("slow: 1500 ms to active (limit 1000)", block)
        self.assertIn("slowest step presented→mapped 1384 ms", block)
        self.assertIn("main thread 1 wchan do_poll", block)
        self.assertNotIn("missing", block)

    def test_missing_stages_are_reported_after_five_seconds(self):
        timeline = self.make_timeline()
        self.run_open(timeline, [("dispatch", 2), ("activate", 3), ("presented", 9)])

        self.clock.at(4900)
        timeline.check_overdue()
        self.assertEqual(self.lines, [])

        self.clock.at(5100)
        timeline.check_overdue()
        [block] = self.lines
        self.assertIn(
            "activate 3 prepared - surface - mapped - presented 9 painted -", block
        )
        self.assertIn(
            "incomplete (overdue) after 5100 ms; missing prepared, surface,"
            " mapped, painted, active",
            block,
        )
        self.assertEqual(self.pending, [True, False])

    def test_close_finishes_at_dispatch(self):
        timeline = self.make_timeline()
        self.clock.at(0)
        timeline.begin("key", x_lag=None, loop=40)
        self.clock.at(2)
        timeline.mark("dispatch", action="close")

        self.assertEqual(self.lines, ["close key→dispatch 2 ms"])

    def test_activation_without_key_press_starts_at_dispatch(self):
        timeline = self.make_timeline()
        self.clock.at(0)
        timeline.mark("dispatch", action="open")

        self.assertEqual(timeline.current.start, "dispatch")
        self.assertEqual(timeline.current.expected()[0], "dispatch")

    def test_stages_without_an_open_are_ignored(self):
        timeline = self.make_timeline()
        timeline.mark("painted")

        self.assertIsNone(timeline.current)
        self.assertEqual(self.lines, [])

    def test_paint_from_an_earlier_open_is_ignored(self):
        timeline = self.make_timeline()
        stale = timeline.begin("key")
        timeline.begin("key")

        timeline.mark("painted", record=stale)

        self.assertNotIn("painted", timeline.current.times)
        self.assertIn("incomplete (superseded)", self.lines[0])


class StallWatchdogTests(TestCase):
    @patch("emote.diag.main_stack", return_value=("picker.py:1 apply_search",))
    def test_late_heartbeat_samples_and_reports_stall(self, _main_stack):
        clock = FakeClock()
        lines = []
        watchdog = diag.StallWatchdog(Mock(), write=lines.append, clock=clock)
        watchdog.request_native_stack = Mock()

        clock.at(1500)
        stall = watchdog.check(None, 100.0)
        self.assertIsNotNone(stall)
        clock.at(3600)
        stall = watchdog.check(stall, 100.0)
        watchdog.request_native_stack.assert_called_once()

        clock.at(3700)
        self.assertIsNone(watchdog.check(stall, 103.65))
        [summary] = lines
        self.assertIn("main loop stall 3400 ms, 2 stack samples", summary)
        self.assertIn("main thread", summary)
        self.assertIn("[2x]\n  picker.py:1 apply_search", summary)

    def test_on_time_heartbeat_is_not_a_stall(self):
        clock = FakeClock()
        watchdog = diag.StallWatchdog(Mock(), write=Mock(), clock=clock)
        clock.at(1200)

        self.assertIsNone(watchdog.check(None, 100.0))

    def test_gdb_output_merges_identical_thread_stacks(self):
        output = (
            "[New LWP 11]\n[New LWP 12]\n[Switching to thread 1]\n\n"
            'Thread 3 (LWP 12 "llvmpipe-1"):\n#0 wait ()\n\n'
            'Thread 2 (LWP 11 "llvmpipe-0"):\n#0 wait ()\n\n'
            'Thread 1 (LWP 10 "emote"):\n#0 poll ()'
        )

        self.assertEqual(
            diag.compact_gdb(output),
            "[Switching to thread 1]\n\n"
            'Thread 3 (LWP 12 "llvmpipe-1"): and 1 more\n#0 wait ()\n\n'
            'Thread 1 (LWP 10 "emote"):\n#0 poll ()',
        )

    @patch("emote.diag.shutil.which", return_value=None)
    def test_native_stack_is_skipped_without_gdb(self, _which):
        lines = []
        diag.capture_native_stack(lines.append)

        self.assertEqual(lines, ["native stack skipped: gdb not on PATH"])
