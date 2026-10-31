<p align="center"><img src="https://massgrave.dev/img/logo_small.png" alt="MAS Logo"></p>

<h1 align="center">Microsoft  Activation  Scripts (MAS)</h1>

<p align="center">Open-source Windows and Office activator featuring HWID, Ohook, TSforge, and Online KMS activation methods, along with advanced troubleshooting.</p>

<hr>
  
## How to Activate Windows / Office / Extended Security Updates (ESU)?

### Method 1 - PowerShell ❤️

1. Click the **Start Menu**, type `PowerShell`, and open it.

2. Copy and paste the code below and press **Enter.**  
   - For **Windows 8.1, 10 and 11**:
     ```
     irm https://get.activated.win | iex
     ```
	 If the above is blocked (by ISP/DNS), try this (needs updated Windows 10 or 11):  
	 ```
	 iex (curl.exe -s --doh-url https://1.1.1.1/dns-query https://get.activated.win | Out-String)
	 ```
	- **Script not launching? Use the below-listed Method 2.**

3. In the menu that appears, type the number corresponding to one of the **Green** options.

---

### Method 2 - Traditional (Windows Vista and later)

1.   Download the script:
      *   [**MAS_AIO.cmd**](https://dev.azure.com/massgrave/Microsoft-Activation-Scripts/_apis/git/repositories/Microsoft-Activation-Scripts/items?path=/MAS/All-In-One-Version-KL/MAS_AIO.cmd&download=true) (Direct script)
      *   [**MAS_AIO.zip**](https://dev.azure.com/massgrave/Microsoft-Activation-Scripts/_apis/git/repositories/Microsoft-Activation-Scripts/items?$format=zip) (If the direct script is blocked by your browser)
2.   Run the `MAS_AIO.cmd` file.
3.   In the menu that appears, type the number corresponding to one of the **Green** options.

---

> [!TIP]
> - Some ISPs/DNS providers block access to our domains. You can bypass this by enabling [DNS-over-HTTPS (DoH)](https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/encrypted-dns-browsers/) in your browser. 
> - **Having trouble**? Visit our [troubleshooting page](https://massgrave.dev/troubleshoot) or raise an issue on [GitHub](https://github.com/massgravel/Microsoft-Activation-Scripts/issues).

> [!NOTE]
>
> - The `irm` command in PowerShell downloads a script from a specified URL, and the `iex` command executes it.
> - Always double-check the URL before executing the command and verify the source is trustworthy when manually downloading files.
> - Be cautious of third parties spreading malware disguised as MAS by altering the URL in the PowerShell command.

---

## Python desktop UI

A standard-library Tkinter launcher is available for the local scripts. It does
not download, rewrite, or automatically run activation scripts.

### Requirements and launch

- Windows 10 version 1809 or later, including Windows 11 (the embedded terminal
  uses Windows ConPTY).
- Native 64-bit Python 3.10 or later with Tkinter installed. The python.org
  Windows installer includes Tkinter. Use ARM64 Python on ARM64 Windows.
- Keep `mas_ui.py`, `mas_terminal.py`, and the `MAS` directory together.

From the repository directory, run:

```powershell
python .\mas_ui.py
```

No pip packages are required. **Check activation status** is selected initially.
Choose a tool and click **Run selected tool** to review a confirmation before
execution. Tools that modify the system require **Restart as administrator**;
approve the Windows UAC prompt, then select and confirm the tool again. Restarting
does not automatically execute a script.

### Embedded controls

- Click the terminal and type a menu key directly; `choice` menus do not need
  Enter. For text prompts, type and press Enter, or use **Send text / Send + Enter**.
- Arrow keys, Backspace, Escape, Tab, Enter, and Ctrl+C are forwarded to the console.
  Use Ctrl+V to paste (multiline pastes require confirmation). Right-click copies
  selected output.
- **Ctrl+C** requests an interrupt. Prefer the script's own exit/back menu.
  **Stop** force-closes the console and its attached applications after confirmation;
  it cannot undo changes already made and may interrupt an in-progress repair.
- **Save displayed output** writes a UTF-8 copy of the current display and retained
  scrollback. Output may contain machine or licensing information; review it before sharing.

The lightweight terminal renders text, cursor movement, and screen clearing, but
not ANSI colors or full terminal emulation. It has a fixed 120-column, 40-row console
and retains up to 2,040 lines. Resizing the window does not resize the console.
Scripts use their existing `-qedit` switch (except the status script) to avoid
relaunching into a separate console. Native-architecture Python is important because
this switch also skips the scripts' architecture relaunch checks.
Any external GUI tools opened by a script remain separate windows.
The wrapper does not change antivirus settings or bypass blocked scripts; Windows
security policy may still prevent a selected script from running.
Missing scripts are marked **[unavailable]** in the tool list and are not restored
or downloaded automatically.
Repository paths containing `%` are rejected to avoid command-shell expansion.
A process exit code is reported as such, not as proof of successful activation.

### Tests

```powershell
python -m unittest discover -s tests -v
```

Tests cover script selection, launch quoting, confirmations, the screen renderer,
Tk widgets, and embedded console input/output and shutdown using harmless commands.
They do not execute MAS scripts or alter licensing settings.

---

<div align="center">
	
### Homepage - [https://massgrave.dev/](https://massgrave.dev/)
  
[![1.1]][1]
[![1.2]][2]
[![1.3]][3]
[![1.4]][4]
[![1.5]][5]
[![1.6]][6]
[![1.7]][7]

[1.1]: https://massgrave.dev/img/logo_discord.png (Chat with us without signup)
[1.2]: https://massgrave.dev/img/logo_reddit.png (Reddit)
[1.3]: https://massgrave.dev/img/logo_bluesky.png (Bluesky)
[1.4]: https://massgrave.dev/img/logo_x.png (Twitter)

[1.5]: https://massgrave.dev/img/logo_github.png (GitHub)
[1.6]: https://massgrave.dev/img/logo_azuredevops.png (AzureDevOps)
[1.7]: https://massgrave.dev/img/logo_gitea.png (Self-hosted Git)

[1]: https://discord.gg/j2yFsV5ZVC
[2]: https://www.reddit.com/r/MAS_Activator
[3]: https://bsky.app/profile/massgrave.dev
[4]: https://twitter.com/massgravel
[5]: https://github.com/massgravel/Microsoft-Activation-Scripts
[6]: https://dev.azure.com/massgrave/_git/Microsoft-Activation-Scripts
[7]: https://git.activated.win/Microsoft-Activation-Scripts

---

Latest Version: 3.12  
Release date: 04-Jul-2026
