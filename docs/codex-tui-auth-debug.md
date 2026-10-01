# Codex TUI vs `exec`: debugging procedure

**Problem:** after upgrading Codex, `codex exec` uses the updated API key but the interactive TUI (`codex`) doesn't.

**Setup:** Rocky Linux remote desktop, VS Code remote terminal, uv venv activated in both cases. The org-managed Azure endpoint uses a custom `base_url`. The key is stored in both `~/.codex/auth.json` and `config.toml` (`openai_api_key`), and both are always updated together. Codex was reinstalled into a user prefix at `~/.npm-global`.

Everything you produce goes into `~/codex-debug`. Every change has a restore step.

---

## Phase 0: Prepare (5 min)

```bash
mkdir -p ~/codex-debug && cd ~/codex-debug
```

Back up both files:

```bash
cp ~/.codex/auth.json ~/codex-debug/auth.json.bak && cp ~/.codex/config.toml ~/codex-debug/config.toml.bak
```

Close **every** Codex session: TUI windows, other terminals, and the VS Code Codex panel (run **Developer: Reload Window**). Then check that nothing is left:

```bash
pgrep -af codex
```

It should print nothing. If something is still running, close it or run `kill <pid>`.

Activate the uv venv as you normally do.

## Phase 1: Write down the exact symptom (most important)

1. Run your usual `codex exec ...` command. Copy the **first lines of the output** (the model and provider) into notes.
2. Start `codex`, send one message, and write down the **exact error text**.
3. In the TUI, type `/status` and note the **model, provider and auth method**.

If the model or provider differ between steps 1 and 3, you've found the problem. Go to Phase 9, fix A.

## Phase 2: Baseline report (prints no secrets)

Save this as `~/codex-debug/diag.sh`:

```bash
#!/usr/bin/env bash
echo "== shell =="; echo "USER=$USER HOME=$HOME VIRTUAL_ENV=${VIRTUAL_ENV:-none}"
env | grep -iE 'codex|openai|azure' | sed 's/=.*/=<set>/' || echo "no related env vars"
echo "== binary =="; type -a codex; alias | grep -i codex
for b in $(type -ap codex); do echo "$b -> $(readlink -f "$b") | $("$b" --version 2>&1)"; done
echo "npm prefix: $(npm config get prefix)"
echo "== processes =="; pgrep -af codex || echo none
echo "== auth.json fields =="
/usr/bin/python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.codex/auth.json'))); [print(' ',k,'->',v if k=='auth_mode' else ('SET' if v else 'empty')) for k,v in d.items()]"
echo "== key copies match? =="
/usr/bin/python3 -c "import json,os,re; a=json.load(open(os.path.expanduser('~/.codex/auth.json'))).get('OPENAI_API_KEY'); c=re.search(r'openai_api_key\s*=\s*[\"\x27](.*?)[\"\x27]', open(os.path.expanduser('~/.codex/config.toml')).read()); print('MATCH' if c and a==c.group(1) else 'DIFFERENT')"
echo "== config.toml (sections + relevant keys, key value hidden) =="
grep -nE '^\[|model|provider|profile|base_url|env_key|wire_api|auth|login|credentials|header|api-version' ~/.codex/config.toml | sed -E 's/(api_key\s*=\s*).*/\1<hidden>/'
echo "== other configs =="; ls -la /etc/codex/ ./.codex/ 2>/dev/null || echo none
echo "== login status =="; codex login status
```

Run it:

```bash
bash ~/codex-debug/diag.sh > ~/codex-debug/diag.txt 2>&1
```

**What to look for in `diag.txt`:**

| What you see | Meaning |
|---|---|
| More than one `codex`, or different versions | An old binary is still being picked up |
| `tokens -> SET` or `auth_mode -> chatgpt` | An old ChatGPT login is overriding the key |
| `credentials_store = "keyring"` or `"auto"` | The TUI may read the key from the keyring, not the files |
| `model_provider` set only inside `[profiles.*]` | The two modes may resolve different providers |
| Files in `/etc/codex/` | Org-managed config may override yours |

## Phase 3: Break-both test (does the TUI read the files at all?)

1. Add `X` to the end of the key in **both** `~/.codex/auth.json` and `~/.codex/config.toml`.
2. Run `codex exec "hi"`. It **should fail**.
3. Run `codex` and send one message.
   - **The TUI behaves exactly as before** → it isn't reading these files. Phases 4–5 will show where it reads from.
   - **The TUI also fails, with the same new error** → both modes read the files, so the difference is elsewhere (model, provider or version).
4. Restore both files:

   ```bash
   cp ~/codex-debug/auth.json.bak ~/.codex/auth.json && cp ~/codex-debug/config.toml.bak ~/.codex/config.toml
   ```

## Phase 4: `strace`, which files each mode actually opens

```bash
which strace || sudo dnf install -y strace
```

`dnf` needs admin rights. Ask IT if you don't have them.

Trace the TUI (send one message, then quit):

```bash
strace -f -e trace=openat,connect -o ~/codex-debug/tui.trace codex
```

Trace `exec`:

```bash
strace -f -e trace=openat,connect -o ~/codex-debug/exec.trace codex exec "hi"
```

Compare:

```bash
grep -E 'auth.json|\.toml|/etc/codex|bus|keyring' ~/codex-debug/tui.trace | grep -v ENOENT | sort -u > ~/codex-debug/tui.files
```

```bash
grep -E 'auth.json|\.toml|/etc/codex|bus|keyring' ~/codex-debug/exec.trace | grep -v ENOENT | sort -u > ~/codex-debug/exec.files
```

```bash
diff ~/codex-debug/tui.files ~/codex-debug/exec.files
```

The process IDs and memory addresses in the traces will also differ. Ignore those and compare the **file paths**.

- **A file opened by only one mode** → that file is what differs.
- **The TUI connects to `/run/user/.../bus`** → it uses the keyring.
- **The TUI never opens `auth.json`** → it gets its credentials from somewhere else.

## Phase 5: Debug logs from both modes

TUI (send one message, then quit):

```bash
RUST_LOG=trace codex
```

`exec`:

```bash
RUST_LOG=trace codex exec "hi" 2> ~/codex-debug/exec-debug.log
```

Compare:

```bash
grep -iE 'auth|provider|base_url|model|401|403|error' ~/.codex/log/codex-tui.log | tail -40
```

```bash
grep -iE 'auth|provider|base_url|model|401|403|error' ~/codex-debug/exec-debug.log | tail -40
```

Compare the **request URL, provider, model and auth method** between the two.

> These logs may contain your key, so check them before sharing with anyone.

## Phase 6: Clean Codex home (is the problem in stored state?)

```bash
mkdir -p ~/codex-test && cp ~/.codex/config.toml ~/codex-test/
```

```bash
CODEX_HOME=~/codex-test codex login --with-api-key
```

Paste the key when asked, then:

```bash
CODEX_HOME=~/codex-test codex
```

- **The TUI works** → something in `~/.codex` is stale. Use fix B in Phase 9.
- **The TUI still fails** → it's the Codex version or the endpoint. Go to Phase 7.

## Phase 7: Old version against new version

This doesn't touch your current install. Get the old version number from the old global binary's `--version` (see the Phase 2 output) or from a colleague who hasn't upgraded.

```bash
npm install --prefix ~/codex-old @openai/codex@<old-version>
```

```bash
~/codex-old/node_modules/.bin/codex
```

- **The old version works** → the upgrade broke it. Use fix D.
- **The old version also fails** → the problem is in your environment or the endpoint. Go to Phase 8.

## Phase 8: Ask the platform team

Give them the time of your failed TUI request and the error text. Ask:

- Did the gateway receive the request, and what did it return?
- Which `wire_api` does it support (`responses` or `chat`), especially for the Claude models?

## Phase 9: Fixes (apply the one your findings point to)

| Finding | Fix |
|---|---|
| **A.** Model or provider differ (Phase 1) | Set `model = ...` and `model_provider = ...` at the **top** of `config.toml`, outside any `[profiles.*]` block |
| **B.** Stale state, tokens, `auth_mode` (Phase 2/6) | Close Codex, run `codex logout`, then `codex login --with-api-key`. Re-add the `openai_api_key` line in `config.toml` if your org's setup needs it |
| **C.** Keyring (Phase 2/4) | Add `cli_auth_credentials_store = "file"` to `config.toml`, then do fix B |
| **D.** Upgrade regression (Phase 7) | `npm install -g @openai/codex@<old-version>` and report the issue |
| **E.** Old binary picked up (Phase 2) | Remove the old binary, check that `~/.npm-global/bin` is first in `PATH`, then run `hash -r` |
| **F.** Running process (Phase 0/4) | Close it or reload the VS Code window, then retry |

**Verify after any fix:** open a new terminal, activate the venv, then run `codex exec "hi"` and `codex` + `/status`. Both should show the same model and provider, and both should work.

## Cleanup

```bash
rm -rf ~/codex-test ~/codex-old
```

Keep `~/codex-debug` until it's fixed, then delete it. It contains backups of your key.

---

## Results to note

- [ ] Exact TUI error text:
- [ ] `/status` (TUI) model / provider / auth:
- [ ] `exec` header model / provider:
- [ ] Phase 3 result:
- [ ] Phase 4 `diff` output:
- [ ] Phase 6 result:
- [ ] Phase 7 result:
