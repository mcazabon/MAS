import os
from pathlib import Path
import queue
import tempfile
import threading
import time
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mas_terminal import ConsoleSession, Screen, encode_input
from mas_ui import Launcher, ROOT, SCRIPTS, Script, command_for


class ScreenTests(unittest.TestCase):
    def test_win32_input_packets(self):
        self.assertEqual(encode_input("Y", True),
                         b"\x1b[89;0;89;1;16;1_\x1b[89;0;89;0;16;1_")
        self.assertIn(b"[38;72;0;1;256;1_", encode_input("\x1b[A", True))
        self.assertIn(b"[67;0;3;1;8;1_", encode_input("\x03", True))
        self.assertIn(b"[8;0;8;1;0;1_", encode_input("\x7f", True))
        self.assertEqual(encode_input("hello\r", False), b"hello\r")

    def test_fragmented_sequences_and_overwriting(self):
        screen = Screen(20, 3)
        for chunk in ("old text\rnew", "\x1b[", "K", "\r\nnext", "\x1b[1;2H!"):
            screen.feed(chunk)
        self.assertEqual(screen.text, "n!w\nnext\n")

    def test_erase_and_ignored_color_and_title(self):
        screen = Screen(20, 3)
        screen.feed("stale\x1b[2J\x1b[H\x1b]0;title\x1b\\\x1b[32mMenu\x1b[0m")
        self.assertEqual(screen.text, "Menu\n\n")

    def test_scroll_and_report_cursor(self):
        screen = Screen(8, 2)
        screen.feed("one\r\ntwo\r\nthree\x1b[6n")
        self.assertEqual(screen.top, 1)
        self.assertEqual(screen.responses, ["\x1b[2;6R"])
        screen.feed("\x1b[Hnew\x1b[K")
        self.assertEqual(screen.text, "one\nnew\nthree")

    def test_erase_scrollback_preserves_saved_cursor(self):
        screen = Screen(8, 2)
        screen.feed("one\r\ntwo\r\nthree\x1b[s\x1b[3J\x1b[u!")
        self.assertEqual(screen.text, "\n     !")

    def test_wrap_backspace_tab_and_saved_cursor(self):
        screen = Screen(8, 3)
        screen.feed("12345678X\bY\x1b[s\tZ\x1b[u!")
        self.assertEqual(screen.lines[0], list("12345678"))
        self.assertEqual(screen.lines[1][:2], list("Y!"))
        self.assertEqual(screen.lines[2], ["Z"])

    def test_scrollback_is_bounded(self):
        screen = Screen()
        screen.feed("line\r\n" * 2200)
        self.assertEqual(len(screen.lines), 2040)
        self.assertLess(screen.row, len(screen.lines))


class CatalogTests(unittest.TestCase):
    def test_all_script_entry_points_are_listed_once(self):
        expected = set((ROOT / "MAS").rglob("*.cmd"))
        actual = [script.path for script in SCRIPTS]
        self.assertTrue(expected.issubset(set(actual)))
        self.assertEqual(len(actual), 10)
        self.assertEqual(len(actual), len(set(actual)))

    def test_command_quotes_path_with_spaces_and_disables_relaunch(self):
        script = SCRIPTS[0]
        with tempfile.TemporaryDirectory(prefix="mas ui & test ") as folder:
            path = Path(folder) / "sample.cmd"
            path.touch()
            with patch.object(Script, "path", new_callable=lambda: property(lambda _: path)):
                self.assertEqual(command_for(script),
                                 f'cmd.exe /d /v:off /s /c ""{path}" -qedit"')

    def test_status_has_no_extra_switches(self):
        self.assertTrue(command_for(SCRIPTS[1]).endswith('Check_Activation_Status.cmd""'))
        self.assertFalse(SCRIPTS[1].admin)

    def test_missing_script_is_an_explicit_error(self):
        with patch.object(Script, "path",
                          new_callable=lambda: property(lambda _: ROOT / "missing.cmd")):
            with self.assertRaises(FileNotFoundError):
                command_for(SCRIPTS[0])

    def test_percent_expansion_is_rejected(self):
        with patch.object(Script, "path",
                          new_callable=lambda: property(lambda _: ROOT / "%PATH%.cmd")):
            with self.assertRaises(ValueError):
                command_for(SCRIPTS[0])


@unittest.skipUnless(os.name == "nt", "Windows console integration")
class ConsoleTests(unittest.TestCase):
    def run_console(self, command, answer=None, stop_after_ready=False, cwd=ROOT,
                    respond_when=None):
        events = queue.Queue()
        session = ConsoleSession(lambda kind, value: events.put((kind, value)))
        thread = threading.Thread(target=session.run, args=(command, cwd), daemon=True)
        thread.start()
        output, errors, code = [], [], None
        deadline = time.monotonic() + 20
        try:
            while time.monotonic() < deadline:
                kind, value = events.get(timeout=max(0.01, deadline - time.monotonic()))
                if kind == "ready":
                    if answer and respond_when is None:
                        session.write(answer)
                    if stop_after_ready:
                        threading.Thread(target=session.stop, daemon=True).start()
                elif kind == "output":
                    output.append(value)
                    if answer and respond_when and respond_when in "".join(output):
                        session.write(answer)
                        answer = None
                elif kind == "error":
                    errors.append(value)
                elif kind == "finished":
                    code = value
                    break
            else:
                self.fail("Console timed out")
        except queue.Empty:
            self.fail("Console timed out waiting for an event")
        finally:
            if thread.is_alive():
                threading.Thread(target=session.stop, daemon=True).start()
            thread.join(timeout=10)
        self.assertFalse(thread.is_alive(), "Console worker did not shut down")
        self.assertEqual(errors, [])
        screen = Screen()
        screen.feed("".join(output))
        return screen.text, code

    def test_choice_accepts_a_key_without_enter(self):
        output, code = self.run_console(
            'cmd.exe /d /c "choice /c YN /n /m CHOOSE & '
            'if errorlevel 2 (echo NO) else (echo ACCEPTED)"',
            answer="Y", respond_when="CHOOSE",
        )
        self.assertIn("ACCEPTED", output)
        self.assertEqual(code, 0)

    def test_set_p_accepts_line_input_and_reports_exit_code(self):
        output, code = self.run_console(
            'cmd.exe /d /v:on /c "set /p answer=Prompt: & echo VALUE=!answer!& exit /b 7"',
            answer="hello\r",
        )
        self.assertIn("VALUE=hello", output)
        self.assertEqual(code, 7)

    def test_batch_path_with_spaces_and_metacharacters(self):
        with tempfile.TemporaryDirectory(prefix="mas ui & test ") as folder:
            path = Path(folder) / "sample.cmd"
            path.write_bytes(b"@echo off\r\necho WRAPPER_OK\r\nexit /b 0\r\n")
            with patch.object(Script, "path", new_callable=lambda: property(lambda _: path)):
                command = command_for(SCRIPTS[0])
            output, code = self.run_console(command, cwd=folder)
            self.assertIn("WRAPPER_OK", output)
            self.assertEqual(code, 0)

    def test_stop_ends_console_session(self):
        _, code = self.run_console('cmd.exe /d /c "pause >nul"', stop_after_ready=True)
        self.assertIsNotNone(code)

    def test_ctrl_c_interrupts_line_input(self):
        _, code = self.run_console(
            'cmd.exe /d /c "set /p answer=INTERRUPT_READY"',
            answer="\x03", respond_when="INTERRUPT_READY",
        )
        self.assertNotEqual(code, 0)

    def test_stop_before_start_does_not_launch_process(self):
        events = []
        session = ConsoleSession(lambda kind, value: events.append((kind, value)))
        session.stop()
        with patch("mas_terminal._kernel") as kernel:
            session.run('cmd.exe /d /c "echo SHOULD_NOT_RUN"', ROOT)
        kernel.assert_not_called()
        self.assertEqual(events, [("finished", None)])

    def test_input_is_rejected_before_start(self):
        session = ConsoleSession(lambda *_: None)
        with self.assertRaises(OSError):
            session.write("x")

    def test_launch_error_is_reported_and_finishes(self):
        events = []
        session = ConsoleSession(lambda kind, value: events.append((kind, value)))
        session.run('cmd.exe /d /c "echo SHOULD_NOT_RUN"', ROOT / "nonexistent-directory")
        self.assertTrue(any(kind == "error" for kind, _ in events))
        self.assertEqual(events[-1], ("finished", None))


@unittest.skipUnless(os.name == "nt", "Windows Tk smoke tests")
class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = Launcher(self.root)

    def tearDown(self):
        self.app.close()

    def test_initial_state_and_output_rendering(self):
        self.assertEqual(self.app.tools.current(), 1)
        self.assertIsNone(self.app.session)
        self.app.events.put(("output", "\x1b[2J\x1b[HEmbedded output"))
        self.root.after_cancel(self.app.poll_id)
        self.app.poll()
        self.root.update_idletasks()
        self.assertTrue(self.app.terminal.get("1.0", "end").startswith("Embedded output"))

    def test_cancel_does_not_start_script(self):
        with patch("mas_ui.messagebox.askokcancel", return_value=False):
            self.app.run()
        self.assertIsNone(self.app.session)

    def test_non_admin_cannot_start_modifying_tool(self):
        self.app.admin = False
        self.app.tools.current(0)
        with patch("mas_ui.messagebox.showwarning") as warning:
            self.app.run()
        warning.assert_called_once()
        self.assertIsNone(self.app.session)

    def test_missing_script_is_shown_as_unavailable(self):
        with patch.object(Script, "path",
                          new_callable=lambda: property(lambda _: ROOT / "missing.cmd")):
            self.app.describe()
        self.assertIn("Unavailable", self.app.description.get())

    def test_finished_does_not_claim_activation_succeeded(self):
        self.app.events.put(("finished", 0))
        self.root.after_cancel(self.app.poll_id)
        self.app.poll()
        self.assertIn("does not confirm activation succeeded", self.app.status.get())
        self.assertFalse(self.app.ready)

    def test_elevation_failure_keeps_window_open(self):
        with patch("mas_ui.messagebox.askokcancel", return_value=True), \
                patch("mas_ui.restart_elevated", side_effect=OSError("Cancelled")), \
                patch("mas_ui.messagebox.showerror") as error:
            self.app.elevate_app()
        error.assert_called_once()
        self.assertTrue(self.root.winfo_exists())

    def test_ui_runs_harmless_interactive_batch_end_to_end(self):
        def wait_for(condition):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                self.root.update()
                if condition():
                    return
                time.sleep(0.01)
            self.fail(f"UI timed out: {self.app.status.get()}")

        with tempfile.TemporaryDirectory(prefix="mas ui test ") as folder:
            path = Path(folder) / "interactive.cmd"
            path.write_bytes(
                b"@echo off\r\n"
                b"choice /c YN /n /m MENU_READY\r\n"
                b"set /p answer=TEXT_READY\r\n"
                b"echo GOT=%answer%\r\n"
                b"exit /b 7\r\n"
            )
            with patch.object(Script, "path", new_callable=lambda: property(lambda _: path)), \
                    patch("mas_ui.messagebox.askokcancel", return_value=True):
                self.app.run()
            try:
                wait_for(lambda: "MENU_READY" in self.app.screen.text)
                self.app.key(SimpleNamespace(keysym="y", char="y", state=0))
                wait_for(lambda: "TEXT_READY" in self.app.screen.text)
                self.app.input.insert(0, "sample")
                self.app.send_line()
                wait_for(lambda: self.app.session is None)
                self.assertIn("GOT=sample", self.app.screen.text)
                self.assertIn("code 7", self.app.status.get())
                self.assertEqual(str(self.app.run_button["state"]), "normal")
            finally:
                if self.app.session:
                    with patch("mas_ui.messagebox.askokcancel", return_value=True):
                        self.app.stop()
                    wait_for(lambda: self.app.session is None)


if __name__ == "__main__":
    unittest.main()
