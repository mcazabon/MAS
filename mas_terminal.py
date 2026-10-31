"""Standard-library Windows pseudoconsole transport and a small VT screen model."""

import codecs
import ctypes
from ctypes import wintypes as w
from pathlib import Path
import os
import queue
import re
import threading


def encode_input(text, win32_mode):
    if not win32_mode:
        return text.encode("utf-8")
    special = {
        "\x1b[A": (38, 72), "\x1b[B": (40, 80),
        "\x1b[C": (39, 77), "\x1b[D": (37, 75),
        "\x1b[H": (36, 71), "\x1b[F": (35, 79), "\x1b[3~": (46, 83),
    }
    packets = []
    while text:
        key = next((key for key in special if text.startswith(key)), None)
        if key:
            virtual, scan = special[key]
            units, control = [0], 0x100
            text = text[len(key):]
        else:
            char, text = text[0], text[1:]
            if char == "\x7f":
                char = "\b"
            scan = control = 0
            virtual = ord(char.upper()) if char.isascii() and char.isalnum() else 0
            if char in "\r\t\b\x1b":
                virtual = ord(char)
            elif 0 < ord(char) < 27:
                virtual, control = ord(char) + 64, 8
            elif char.isascii() and char.isupper():
                control = 0x10
            encoded = char.encode("utf-16-le")
            units = [int.from_bytes(encoded[index:index + 2], "little")
                     for index in range(0, len(encoded), 2)]
        for unit in units:
            for down in (1, 0):
                packets.append(f"\x1b[{virtual};{scan};{unit};{down};{control};1_")
    return "".join(packets).encode("ascii")


class Screen:
    """Render the cursor movement and erase sequences used by console menus."""

    def __init__(self, columns=120, rows=40):
        self.columns = columns
        self.rows = rows
        self.lines = [[] for _ in range(rows)]
        self.row = self.column = self.top = 0
        self.saved = (0, 0)
        self.state = ""
        self.sequence = ""
        self.responses = []

    def feed(self, text):
        for char in text:
            if self.state == "osc":
                if char == "\a" or (self.sequence.endswith("\x1b") and char == "\\"):
                    self.state = self.sequence = ""
                else:
                    self.sequence = char
                continue
            if self.state == "esc":
                self.state = ""
                if char == "[":
                    self.state, self.sequence = "csi", ""
                elif char == "]":
                    self.state, self.sequence = "osc", ""
                elif char == "7":
                    self.saved = (self.row, self.column)
                elif char == "8":
                    self.row, self.column = self.saved
                continue
            if self.state == "csi":
                if "@" <= char <= "~":
                    self._csi(char, self.sequence)
                    self.state = self.sequence = ""
                elif len(self.sequence) < 128:
                    self.sequence += char
                else:
                    self.state = self.sequence = ""
                continue
            if char == "\x1b":
                self.state = "esc"
            elif char == "\r":
                self.column = 0
            elif char == "\n":
                self._down()
            elif char == "\b":
                self.column = max(0, self.column - 1)
            elif char == "\t":
                self.column = min(self.columns, (self.column // 8 + 1) * 8)
            elif char >= " " and char != "\x7f":
                if self.column >= self.columns:
                    self.column = 0
                    self._down()
                line = self.lines[self.row]
                line.extend(" " for _ in range(self.column + 1 - len(line)))
                line[self.column] = char
                self.column += 1

    def _down(self):
        self.row += 1
        if self.row >= len(self.lines):
            self.lines.append([])
        self.top = max(self.top, self.row - self.rows + 1)
        if len(self.lines) > 2040:
            del self.lines[0]
            self.row -= 1
            self.top -= 1
            self.saved = (max(0, self.saved[0] - 1), self.saved[1])

    def _csi(self, command, sequence):
        private = sequence.startswith("?")
        fields = sequence.lstrip("?").split(";")
        if not all(not value or value.isdigit() for value in fields):
            return
        values = [int(value or 0) for value in fields]
        count = values[0] or 1
        if command in ("H", "f"):
            self.row = self.top + min(self.rows, count) - 1
            self.column = min(self.columns, (values[1] or 1) if len(values) > 1 else 1) - 1
        elif command == "A":
            self.row = max(self.top, self.row - count)
        elif command == "B":
            self.row = min(self.top + self.rows - 1, self.row + count)
        elif command == "C":
            self.column = min(self.columns - 1, self.column + count)
        elif command == "D":
            self.column = max(0, self.column - count)
        elif command == "G":
            self.column = min(self.columns, count) - 1
        elif command == "d":
            self.row = self.top + min(self.rows, count) - 1
        elif command == "J":
            if values[0] in (2, 3):
                if values[0] == 3:
                    self.saved = (max(0, self.saved[0] - self.top), self.saved[1])
                    del self.lines[:self.top]
                    self.row -= self.top
                    self.top = 0
                for row in range(self.top, len(self.lines)):
                    self.lines[row] = []
            elif values[0] == 0:
                del self.lines[self.row][self.column:]
                for row in range(self.row + 1, len(self.lines)):
                    self.lines[row] = []
            elif values[0] == 1:
                for row in range(self.top, self.row):
                    self.lines[row] = []
                self._erase_start()
        elif command == "K":
            if values[0] == 0:
                del self.lines[self.row][self.column:]
            elif values[0] == 1:
                self._erase_start()
            elif values[0] == 2:
                self.lines[self.row] = []
        elif command == "s":
            self.saved = (self.row, self.column)
        elif command == "u":
            self.row, self.column = self.saved
        elif command == "n" and not private:
            if values[0] == 6:
                self.responses.append(f"\x1b[{self.row - self.top + 1};{self.column + 1}R")
            elif values[0] == 5:
                self.responses.append("\x1b[0n")
        elif command == "c":
            self.responses.append("\x1b[?1;0c")

    def _erase_start(self):
        line = self.lines[self.row]
        end = min(len(line), self.column + 1)
        line[:end] = [" "] * end

    @property
    def text(self):
        return "\n".join("".join(line).rstrip() for line in self.lines)


class _COORD(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class _STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ("cb", w.DWORD), ("lpReserved", w.LPWSTR), ("lpDesktop", w.LPWSTR),
        ("lpTitle", w.LPWSTR), ("dwX", w.DWORD), ("dwY", w.DWORD),
        ("dwXSize", w.DWORD), ("dwYSize", w.DWORD),
        ("dwXCountChars", w.DWORD), ("dwYCountChars", w.DWORD),
        ("dwFillAttribute", w.DWORD), ("dwFlags", w.DWORD),
        ("wShowWindow", w.WORD), ("cbReserved2", w.WORD),
        ("lpReserved2", ctypes.POINTER(w.BYTE)),
        ("hStdInput", w.HANDLE), ("hStdOutput", w.HANDLE), ("hStdError", w.HANDLE),
    ]


class _STARTUPINFOEX(ctypes.Structure):
    _fields_ = [("StartupInfo", _STARTUPINFO), ("lpAttributeList", ctypes.c_void_p)]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", w.HANDLE), ("hThread", w.HANDLE),
        ("dwProcessId", w.DWORD), ("dwThreadId", w.DWORD),
    ]


def _kernel():
    if os.name != "nt":
        raise OSError("The embedded terminal requires Windows 10 version 1809 or later.")
    dll = ctypes.WinDLL("kernel32", use_last_error=True)
    if not hasattr(dll, "CreatePseudoConsole"):
        raise OSError("The embedded terminal requires Windows 10 version 1809 or later.")
    signatures = {
        "CreatePipe": ([ctypes.POINTER(w.HANDLE), ctypes.POINTER(w.HANDLE),
                        ctypes.c_void_p, w.DWORD], w.BOOL),
        "CloseHandle": ([w.HANDLE], w.BOOL),
        "CreatePseudoConsole": ([_COORD, w.HANDLE, w.HANDLE, w.DWORD,
                                 ctypes.POINTER(w.HANDLE)], ctypes.c_long),
        "ClosePseudoConsole": ([w.HANDLE], None),
        "InitializeProcThreadAttributeList": ([ctypes.c_void_p, w.DWORD, w.DWORD,
                                               ctypes.POINTER(ctypes.c_size_t)], w.BOOL),
        "UpdateProcThreadAttribute": ([ctypes.c_void_p, w.DWORD, ctypes.c_size_t,
                                       ctypes.c_void_p, ctypes.c_size_t,
                                       ctypes.c_void_p, ctypes.c_void_p], w.BOOL),
        "DeleteProcThreadAttributeList": ([ctypes.c_void_p], None),
        "CreateProcessW": ([w.LPCWSTR, w.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                            w.BOOL, w.DWORD, ctypes.c_void_p, w.LPCWSTR,
                            ctypes.POINTER(_STARTUPINFOEX),
                            ctypes.POINTER(_PROCESS_INFORMATION)], w.BOOL),
        "ReadFile": ([w.HANDLE, ctypes.c_void_p, w.DWORD,
                       ctypes.POINTER(w.DWORD), ctypes.c_void_p], w.BOOL),
        "WriteFile": ([w.HANDLE, ctypes.c_void_p, w.DWORD,
                        ctypes.POINTER(w.DWORD), ctypes.c_void_p], w.BOOL),
        "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
        "GetExitCodeProcess": ([w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(dll, name)
        function.argtypes, function.restype = arguments, result
    return dll


def _check(result):
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return result


class ConsoleSession:
    """Run on a worker thread; emit (output|ready|error|finished, payload) events."""

    def __init__(self, emit):
        self.emit = emit
        self.stopped = threading.Event()
        self._lock = threading.Lock()
        self._console = None
        self._input = None
        self._dll = None
        self._pending = queue.Queue()
        self._win32_input = False

    def write(self, text, *, terminal_response=False):
        with self._lock:
            if self._input is None or self.stopped.is_set():
                raise OSError("The console is not accepting input.")
            self._pending.put((text, terminal_response))

    def _write(self):
        while True:
            item = self._pending.get()
            if item is None:
                return
            text, terminal_response = item
            data = encode_input(text, self._win32_input and not terminal_response)
            try:
                while data and not self.stopped.is_set():
                    written = w.DWORD()
                    _check(self._dll.WriteFile(self._input, data, len(data),
                                              ctypes.byref(written), None))
                    if not written.value:
                        raise OSError("The console accepted no input.")
                    data = data[written.value:]
            except OSError as error:
                if not self.stopped.is_set():
                    self.emit("error", f"Console input failed: {error}")
                return

    def stop(self):
        """May block while output drains; always call from a worker thread."""
        self.stopped.set()
        self._close_console()

    def _close_console(self):
        with self._lock:
            console, self._console = self._console, None
        if console is not None:
            self._dll.ClosePseudoConsole(console)

    def run(self, command, cwd):
        handles = []
        attributes = None
        attributes_initialized = False
        reader = None
        writer = None
        exit_code = None
        try:
            if self.stopped.is_set():
                return
            self._dll = dll = _kernel()
            input_read, input_write = w.HANDLE(), w.HANDLE()
            output_read, output_write = w.HANDLE(), w.HANDLE()
            for read, write in ((input_read, input_write), (output_read, output_write)):
                _check(dll.CreatePipe(ctypes.byref(read), ctypes.byref(write), None, 0))
                handles.extend((read, write))
            console = w.HANDLE()
            result = dll.CreatePseudoConsole(_COORD(120, 40), input_read, output_write,
                                             0, ctypes.byref(console))
            if result < 0:
                raise OSError(f"CreatePseudoConsole failed (HRESULT 0x{result & 0xffffffff:08X}).")
            with self._lock:
                self._console = console
                self._input = input_write
            for handle in (input_read, output_write):
                dll.CloseHandle(handle)
                handles.remove(handle)
            reader = threading.Thread(target=self._read, args=(output_read,), daemon=True)
            reader.start()
            size = ctypes.c_size_t()
            dll.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
            attributes = ctypes.create_string_buffer(size.value)
            _check(dll.InitializeProcThreadAttributeList(attributes, 1, 0, ctypes.byref(size)))
            attributes_initialized = True
            _check(dll.UpdateProcThreadAttribute(attributes, 0, 0x00020016, console,
                                                 ctypes.sizeof(console), None, None))
            startup = _STARTUPINFOEX()
            startup.StartupInfo.cb = ctypes.sizeof(startup)
            # Null standard handles let ConPTY initialize them instead of inheriting
            # Python's redirected console handles (for example when launched by an IDE).
            startup.StartupInfo.dwFlags = 0x00000100
            startup.lpAttributeList = ctypes.cast(attributes, ctypes.c_void_p)
            process = _PROCESS_INFORMATION()
            executable = str(Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe")
            if self.stopped.is_set():
                return
            _check(dll.CreateProcessW(executable, ctypes.create_unicode_buffer(command),
                                     None, None, False, 0x00080000, None, str(cwd),
                                     ctypes.byref(startup), ctypes.byref(process)))
            handles.extend((process.hProcess, process.hThread))
            writer = threading.Thread(target=self._write, daemon=True)
            writer.start()
            self.emit("ready", None)
            if self.stopped.is_set():
                self._close_console()
            result = dll.WaitForSingleObject(process.hProcess, 0xffffffff)
            if result != 0:
                raise ctypes.WinError(ctypes.get_last_error())
            code = w.DWORD()
            _check(dll.GetExitCodeProcess(process.hProcess, ctypes.byref(code)))
            exit_code = code.value
        except (OSError, KeyError) as error:
            self.emit("error", str(error))
        finally:
            self._close_console()
            if reader is not None:
                reader.join()
            self._pending.put(None)
            if writer is not None:
                writer.join()
            with self._lock:
                self._input = None
            if attributes_initialized:
                self._dll.DeleteProcThreadAttributeList(attributes)
            for handle in reversed(handles):
                self._dll.CloseHandle(handle)
            self.emit("finished", exit_code)

    def _read(self, handle):
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        buffer = ctypes.create_string_buffer(16384)
        size = w.DWORD()
        tail = ""
        while self._dll.ReadFile(handle, buffer, len(buffer), ctypes.byref(size), None):
            if not size.value:
                break
            text = decoder.decode(buffer.raw[:size.value])
            modes = list(re.finditer(r"\x1b\[\?9001([hl])", tail + text))
            if modes:
                self._win32_input = modes[-1][1] == "h"
            tail = (tail + text)[-16:]
            self.emit("output", text)
        error = ctypes.get_last_error()
        if error not in (0, 109, 232) and not self.stopped.is_set():
            self.emit("error", str(ctypes.WinError(error)))
        remaining = decoder.decode(b"", final=True)
        if remaining:
            self.emit("output", remaining)
