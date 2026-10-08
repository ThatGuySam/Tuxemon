# Terminal Interface

## Sub-features

The Mac curses adaptation exposes all nine composers, scenarios, exact preview, meaning selection, authored quest outcomes, a journal, typing toggle, and Ollama NPC conversation and optional player drafting. It has its own input mapping and layout. Terminal success does not establish ROM or physical Chromatic behavior.

## How to get to it (user POV)

Launch `venv/chromatic/bin/python -m chromatic_demo.terminal --provider ollama --model gemma4:26b-mlx` from the repository root, or double-click `chromatic_demo/Start Text Playground.command`. The named model must already exist locally. Return or `a` activates every selectable option, including editor chips. Arrows move. F1 opens Start from any screen. Tab switches between buttons and typing. In typing mode, Return previews and another Return sends to Ollama. Continue conversation clears the sent draft. Optional Quest actions are scripted and require a separate confirmation.

## Driving it with the PTY Harness

Launch and doctor: verify the local dependencies, then run the focused menu regression. Each test starts a fresh process and waits for the actual title before driving it.

```sh
venv/chromatic/bin/python -c 'import curses, pyte, pytest'
venv/chromatic/bin/python -m pytest -o addopts='' tests/chromatic_demo/test_terminal_e2e.py -k return_selects -q
```

Drive all offline user paths:

```sh
venv/chromatic/bin/python -m pytest -o addopts='' tests/chromatic_demo/test_terminal_e2e.py tests/chromatic_demo/test_terminal_disconnect.py -q
```

The suite sends real keyboard bytes through a controlling PTY and decodes curses output with pyte, including ncurses scroll regions. PTY cases never import or mutate application state. Separate unit checks exercise stale-request and timeout behavior directly. Assertions inspect the visible phase, exact draft, selected menu item, confirmation prompt, journal inventory and flags, and exit status. All nine methods enter text through their own mechanisms, including SPELL for initials, direction traces, grouped letters and the tree. A full quest visits every scenario through menus.

For real Ollama drafting and in-flight cancellation, explicitly opt in to the installed model:

```sh
OLLAMA_E2E_MODEL=gemma4:26b-mlx venv/chromatic/bin/python -m pytest -o addopts='' tests/chromatic_demo/test_terminal_e2e.py tests/chromatic_demo/test_terminal_disconnect.py -k live_ollama -q
```

This sends trial text to the local Ollama endpoint. It neither replaces that service nor uses ChatGPT credentials. The test checks successful generation and retained draft after cancellation; it does not score prose quality or model faithfulness.

Evidence: each test retains `actions.json`, `screen.txt`, and raw terminal output in a unique directory beneath `build/chromatic/terminal-e2e/`. Override that root with `TERMINAL_E2E_EVIDENCE`. Failed expectations print the directory and actual screen. Read the action history to distinguish intermediate screens from final output.

Cleanup: pytest finalizers send Ctrl-C to the owned PTY, then terminate only its process group if needed. Evidence remains. A successful menu-quit test also checks exit status zero. Verify that the emitted evidence directory still contains all three files after the run. No existing Terminal window, Ollama server, ROM process, or device is owned by this harness.

## Gotchas

POSIX PTYs are required; Windows skips these tests. The default run skips live Ollama deliberately. Report that skip as an unverified model boundary until the opt-in test passes. Authored-mode success tests terminal navigation and quest guards, not inference. No ROM build, flashing, installation, Git mutation, or external publication is part of this path. The first run that added the regression recorded Return on Scenarios resetting selection to Resume; preserve its red evidence when diagnosing this class of failure.

## Recorded Disconnect Regression

The October 8 recording showed highlighted chips returning to the menu while the draft stayed empty. Keystrokes were not visible. A separate PTY reproduction used Down, Down, Return on `one` and confirmed that behavior. The regression sends those PTY bytes and expects `Draft (3/96): |one|`. All nine input methods run with both A and Return activation. The older Scenarios test now opens Start with F1 and retains its Return-selection assertions.

`test_terminal_disconnect.py` owns a synthetic HTTP server on an ephemeral loopback port. It verifies actual curses Send requests, two turns, exact text and history in the outgoing prompt, cancellation, server failures, empty replies and 60x20 reading. These fixtures are transport proof, not real inference. Socket binding requires permission in restricted environments; report that block rather than counting an error as a pass. State checks cover every stale-request identity field and the worker timeout path.

The opt-in live NPC test sends a name, asks the NPC to recall it, checks the generated reply screen and unchanged inventory. Inspect the saved reply text for semantic quality; the deterministic transport tests establish role and context plumbing separately. The existing live drafting test still verifies the optional player rewrite path.
