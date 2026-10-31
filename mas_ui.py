"""Tkinter launcher for the repository's unmodified MAS scripts."""

import ctypes
from dataclasses import dataclass
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from mas_terminal import ConsoleSession, Screen


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Script:
    name: str
    relative_path: str
    description: str
    admin: bool = True
    quickedit: bool = True

    @property
    def path(self):
        return ROOT / "MAS" / Path(self.relative_path)


SCRIPTS = (
    Script("All-in-one menu", r"All-In-One-Version-KL\MAS_AIO.cmd",
           "Open the complete MAS menu, including activation and maintenance tools."),
    Script("Check activation status", r"Separate-Files-Version\Check_Activation_Status.cmd",
           "Display Windows and Office licensing and activation status.",
           admin=False, quickedit=False),
    Script("HWID activation", r"Separate-Files-Version\Activators\HWID_Activation.cmd",
           "Open the Windows HWID activation script."),
    Script("Ohook activation", r"Separate-Files-Version\Activators\Ohook_Activation_AIO.cmd",
           "Open the Office Ohook activation and removal menu."),
    Script("TSforge activation", r"Separate-Files-Version\Activators\TSforge_Activation.cmd",
           "Open the TSforge activation menu for supported Microsoft products."),
    Script("Online KMS activation", r"Separate-Files-Version\Activators\Online_KMS_Activation.cmd",
           "Open the Online KMS activation and configuration menu."),
    Script("Change Windows edition", r"Separate-Files-Version\Change_Windows_Edition.cmd",
           "Open tools for changing the installed Windows edition."),
    Script("Change Office edition", r"Separate-Files-Version\Change_Office_Edition.cmd",
           "Open tools for changing the installed Office edition."),
    Script("Extract OEM folder", r"Separate-Files-Version\Extract_OEM_Folder.cmd",
           "Open the OEM folder extraction menu for deployment."),
    Script("Troubleshoot", r"Separate-Files-Version\Troubleshoot.cmd",
           "Open MAS diagnostics and repair tools. Repair actions can change system settings."),
)


def command_for(script):
    path = script.path
    if any(char in str(path) for char in ('%', '"', '\r', '\n')):
        raise ValueError("Move the repository to a path without %, quotes, or line breaks.")
    if not path.is_file():
        raise FileNotFoundError(f"Script not found: {path}")
    argument = " -qedit" if script.quickedit else ""
    return f'cmd.exe /d /v:off /s /c ""{path}"{argument}"'


def is_admin():
    if os.name != "nt":
        return False
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def restart_elevated():
    execute = ctypes.WinDLL("shell32", use_last_error=True).ShellExecuteW
    execute.argtypes = [
        ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
        ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int,
    ]
    execute.restype = ctypes.c_void_p
    result = execute(None, "runas", sys.executable,
                     subprocess.list2cmdline([str(Path(__file__).resolve())]), str(ROOT), 1)
    if not result or result <= 32:
        raise OSError(f"Administrator restart was cancelled or failed (ShellExecute code {result}).")


class Launcher:
    def __init__(self, root):
        self.root = root
        self.session = None
        self.screen = Screen()
        self.events = queue.Queue()
        self.closing = False
        self.ready = False
        self.failed = False
        self.stopping = False
        self.admin = is_admin()
        root.title("MAS - Python Launcher")
        root.geometry("1180x800")
        root.minsize(850, 600)
        root.protocol("WM_DELETE_WINDOW", self.close)

        header = ttk.Frame(root, padding=12)
        header.pack(fill="x")
        ttk.Label(header, text="Microsoft Activation Scripts", font=("Segoe UI", 17, "bold")).pack(
            side="left")
        self.elevate = ttk.Button(header, text="Restart as administrator", command=self.elevate_app)
        self.elevate.pack(side="right")
        if self.admin:
            self.elevate.configure(text="Running as administrator", state="disabled")

        selection = ttk.Frame(root, padding=(12, 0, 12, 8))
        selection.pack(fill="x")
        ttk.Label(selection, text="Tool:").pack(side="left", padx=(0, 8))
        self.tools = ttk.Combobox(selection, state="readonly",
                                  values=[script.name + ("" if script.path.is_file() else " [unavailable]")
                                          for script in SCRIPTS], width=34)
        self.tools.current(1)
        self.tools.pack(side="left")
        self.tools.bind("<<ComboboxSelected>>", self.describe)
        self.run_button = ttk.Button(selection, text="Run selected tool", command=self.run)
        self.run_button.pack(side="left", padx=8)
        self.stop_button = ttk.Button(selection, text="Stop", command=self.stop, state="disabled")
        self.stop_button.pack(side="left")
        ttk.Button(selection, text="Save displayed output", command=self.save).pack(side="right")

        self.description = tk.StringVar()
        ttk.Label(root, textvariable=self.description, padding=(12, 0, 12, 8),
                  wraplength=1050).pack(fill="x")
        ttk.Label(root, text="Click the terminal and type menu keys directly. Enter submits text; "
                  "Ctrl+C interrupts. Right-click to copy selected text.",
                  padding=(12, 0, 12, 8)).pack(fill="x")
        self.terminal = ScrolledText(root, wrap="none", bg="#101820", fg="#e7edf2",
                                     insertbackground="#ffffff", font=("Consolas", 10),
                                     state="disabled", takefocus=True)
        self.terminal.pack(fill="both", expand=True, padx=12)
        self.terminal.bind("<KeyPress>", self.key)
        self.terminal.bind("<<Paste>>", self.paste)
        self.terminal.bind("<<Copy>>", self.copy)
        self.terminal.bind("<Button-3>", self.copy)

        controls = ttk.Frame(root, padding=12)
        controls.pack(fill="x")
        ttk.Label(controls, text="Send text:").pack(side="left")
        self.input = ttk.Entry(controls)
        self.input.pack(side="left", fill="x", expand=True, padx=8)
        self.input.bind("<Return>", self.send_line)
        self.send_button = ttk.Button(controls, text="Send + Enter", command=self.send_line,
                                      state="disabled")
        self.send_button.pack(side="left")
        self.enter_button = ttk.Button(controls, text="Enter", command=lambda: self.send("\r"),
                                       state="disabled")
        self.enter_button.pack(side="left", padx=8)
        self.interrupt_button = ttk.Button(controls, text="Ctrl+C",
                                           command=lambda: self.send("\x03"), state="disabled")
        self.interrupt_button.pack(side="left")
        self.status = tk.StringVar(value="Ready. No scripts have been executed.")
        ttk.Label(root, textvariable=self.status, padding=(12, 0, 12, 10)).pack(fill="x")
        self.describe()
        self.poll_id = root.after(40, self.poll)

    def describe(self, _event=None):
        script = SCRIPTS[self.tools.current()]
        suffix = " Requires administrator privileges." if script.admin else ""
        if not script.path.is_file():
            suffix += " Unavailable: the local script is missing or blocked."
        self.description.set(script.description + suffix)

    def run(self):
        if self.session:
            return
        script = SCRIPTS[self.tools.current()]
        if script.admin and not self.admin:
            messagebox.showwarning("Administrator required",
                                   "Use 'Restart as administrator', approve the Windows UAC prompt, "
                                   "then select and run the tool again.", parent=self.root)
            return
        try:
            command = command_for(script)
        except (OSError, ValueError) as error:
            messagebox.showerror("Cannot run tool", str(error), parent=self.root)
            return
        if not messagebox.askokcancel(
            "Run MAS tool?",
            f"{script.name}\n\n{script.description}\n\n{script.path}\n\n"
            "This executes the local script with your current privileges. "
            "Actions selected in its menus may modify Windows, Office, or licensing settings. "
            "Only continue on a system you are authorized to manage.",
            parent=self.root,
        ):
            return
        self.screen = Screen()
        self.render()
        self.failed = self.stopping = False
        self.session = ConsoleSession(lambda kind, value: self.events.put((kind, value)))
        self.set_running(True)
        self.status.set(f"Starting {script.name}...")
        threading.Thread(target=self.session.run, args=(command, script.path.parent),
                         daemon=True).start()

    def set_running(self, running):
        self.tools.configure(state="disabled" if running else "readonly")
        self.run_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        if not self.admin:
            self.elevate.configure(state="disabled" if running else "normal")
        if not running:
            self.ready = False
        for button in (self.send_button, self.enter_button, self.interrupt_button):
            button.configure(state="normal" if running and self.ready else "disabled")

    def send(self, text):
        if self.session and self.ready:
            try:
                self.session.write(text)
            except OSError as error:
                self.failed = True
                self.status.set(f"Input failed: {error}")

    def send_line(self, _event=None):
        if self.ready:
            self.send(self.input.get() + "\r")
            self.input.delete(0, "end")
        return "break"

    def key(self, event):
        if event.state & 4 and event.keysym.lower() == "v":
            return self.paste()
        keys = {
            "Return": "\r", "KP_Enter": "\r", "BackSpace": "\x7f", "Tab": "\t",
            "Escape": "\x1b", "Up": "\x1b[A", "Down": "\x1b[B",
            "Right": "\x1b[C", "Left": "\x1b[D", "Home": "\x1b[H",
            "End": "\x1b[F", "Delete": "\x1b[3~",
        }
        self.send(keys.get(event.keysym, event.char))
        return "break"

    def paste(self, _event=None):
        try:
            text = self.root.clipboard_get()
        except tk.TclError as error:
            messagebox.showerror("Paste failed", str(error), parent=self.root)
            return "break"
        if "\r" in text or "\n" in text:
            if not messagebox.askokcancel("Paste multiple lines?",
                                          "Line breaks can submit menu choices or commands. Continue?",
                                          parent=self.root):
                return "break"
        self.send(text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r"))
        return "break"

    def copy(self, _event=None):
        if self.terminal.tag_ranges("sel"):
            self.root.clipboard_clear()
            self.root.clipboard_append(self.terminal.get("sel.first", "sel.last"))
        return "break"

    def render(self):
        bottom = self.terminal.yview()[1] >= 0.98
        position = self.terminal.yview()[0]
        self.terminal.configure(state="normal")
        self.terminal.delete("1.0", "end")
        self.terminal.insert("1.0", self.screen.text)
        self.terminal.mark_set("insert", f"{self.screen.row + 1}.{self.screen.column}")
        self.terminal.configure(state="disabled")
        if bottom:
            self.terminal.see("end")
        else:
            self.terminal.yview_moveto(position)

    def poll(self):
        changed = False
        # Bound each batch so heavy script output cannot starve Tk's event loop.
        for _ in range(200):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "output":
                self.screen.feed(value)
                changed = True
                for response in self.screen.responses:
                    if self.session and not self.stopping:
                        try:
                            self.session.write(response, terminal_response=True)
                        except OSError as error:
                            self.failed = True
                            self.status.set(f"Terminal response failed: {error}")
                self.screen.responses.clear()
            elif kind == "ready":
                self.ready = not self.stopping
                self.set_running(True)
                if not self.stopping:
                    self.status.set("Running. Click the terminal to send menu keys.")
                    self.terminal.focus_set()
            elif kind == "error":
                self.failed = True
                self.status.set(f"Console error: {value}")
                messagebox.showerror("Console error", value, parent=self.root)
            elif kind == "finished":
                self.session = None
                self.set_running(False)
                if self.stopping:
                    self.status.set("Stopped. Changes already made by the script are not undone.")
                elif not self.failed:
                    self.status.set(f"Process exited with code {value}. "
                                    "Review the output; this does not confirm activation succeeded.")
                if self.closing:
                    self.root.destroy()
                    return
        if changed:
            self.render()
        self.poll_id = self.root.after(40, self.poll)

    def stop(self):
        if self.session and not self.stopping:
            if not messagebox.askokcancel(
                "Stop running tool?",
                "Stopping a repair or system change midway may leave it incomplete. "
                "Prefer exiting through the script's menu. Force stop anyway?",
                parent=self.root,
            ):
                return False
            self.stopping = True
            self.ready = False
            self.set_running(True)
            self.stop_button.configure(state="disabled")
            self.status.set("Stopping console processes...")
            threading.Thread(target=self.session.stop, daemon=True).start()
        return True

    def close(self):
        if self.session:
            if self.stop():
                self.closing = True
        else:
            self.root.after_cancel(self.poll_id)
            self.root.destroy()

    def elevate_app(self):
        if not messagebox.askokcancel("Restart as administrator?",
                                      "Windows will ask for administrator permission. "
                                      "No script will run automatically after restarting.",
                                      parent=self.root):
            return
        try:
            restart_elevated()
        except OSError as error:
            messagebox.showerror("Restart failed", str(error), parent=self.root)
            return
        self.close()

    def save(self):
        name = filedialog.asksaveasfilename(parent=self.root, defaultextension=".txt",
                                            filetypes=[("Text files", "*.txt")])
        if name:
            try:
                Path(name).write_text(self.terminal.get("1.0", "end-1c"), encoding="utf-8")
            except OSError as error:
                messagebox.showerror("Save failed", str(error), parent=self.root)
            else:
                self.status.set(f"Displayed output saved to {name}")


def main():
    if os.name != "nt" or sys.getwindowsversion().build < 17763:
        raise SystemExit("This launcher requires Windows 10 version 1809 or later.")
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        raise SystemExit("Use native 64-bit Python to keep MAS scripts inside the embedded console.")
    root = tk.Tk()
    Launcher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
