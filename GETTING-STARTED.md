# Getting started on a Windows PC

Zero to a modded ROM running in an emulator. Every step has a way to
check it worked before you move on.

You'll need your own NHL '94 ROM. Nothing in this repository contains
one.

---

## Prefer a .exe? (no Python at all)

There's a prebuilt Windows executable — skip Steps 0 and 1 entirely:

1. Go to the repo's **Actions** tab → **Build Windows exe** → the newest
   run → download **genesis-toolkit-windows** at the bottom.
2. Unzip it. You get `genesis-toolkit.exe`, a `maps` folder, and these docs.
3. Put your ROM next to the exe and continue from **Step 2**, using
   `genesis-toolkit.exe` wherever the guide says `genesis-toolkit`.

If no run is listed yet, click **Run workflow** on that page — it takes
a couple of minutes.

The exe covers everything in this guide. Only `build` and `verify` fall
outside it, since those need an assembler that can't be bundled.

---

## Step 0 — Install Python

The toolkit needs **Python 3.10 or newer**. Check what you have by
opening Command Prompt (press `Win+R`, type `cmd`, press Enter) and
running:

```
python --version
```

**Expect:** `Python 3.11.x` or similar. If you get "not recognized" or a
version below 3.10, install it from [python.org](https://www.python.org/downloads/)
and **tick "Add python.exe to PATH"** on the first screen of the
installer. Then close and reopen Command Prompt.

---

## Step 1 — Get the toolkit

If you have Git:

```
git clone https://github.com/AtomicGameRoom84/NHL-94-Remixed
cd NHL-94-Remixed\toolkit
```

If you don't: open the repository on GitHub, click the green
**Code → Download ZIP**, unzip it, and `cd` into the `toolkit` folder
inside.

Then install:

```
pip install -e .
```

This pulls in `capstone` (the disassembler engine) automatically. If you
also want to run the project's own unit tests, use
`pip install -e ".[test]"` instead — it adds the test runner.

**Check it worked:**

```
genesis-toolkit --help
```

**Expect:** a usage line listing 13 commands — `header`, `vectors`,
`disasm`, `build`, `verify`, `patch`, `fix-checksum`, `ips-create`,
`ips-apply`, `map-list`, `map-set`, `selftest`, `consts`.

> **If `genesis-toolkit` isn't recognised** but `pip install` succeeded,
> use `python -m genesis_toolkit.cli` in place of `genesis-toolkit`
> everywhere below. Same thing, longer to type.

---

## Step 2 — Put your ROM somewhere sensible

Copy your ROM into the `toolkit` folder and **rename it `nhl94.md`**.

That rename matters more than it looks: the original filename,
`NHL '94 (USA, Europe).md`, contains an apostrophe and spaces, which
Windows Command Prompt handles badly. Renaming it saves you a category
of confusing quoting errors. (I hit exactly this while building the
toolkit.)

Keep your untouched original somewhere else as a backup. The toolkit
never writes to your input file — every command writes to a new file you
name — but a spare copy costs nothing.

**Check it worked:**

```
genesis-toolkit header nhl94.md
```

**Expect:**

```
Console name     : 'SEGA GENESIS'
Domestic title   : "NHL Hockey '94"
Checksum         : declared=0x5512 computed=0x5512 ok=True
ROM range        : 0x00000000-0x000fffff
Region codes     : 'UE'
```

`ok=True` is the one to look at — it means the ROM is intact and
readable.

---

## Step 3 — Verify everything at once

```
genesis-toolkit selftest nhl94.md --map maps\nhl94-ue.json
```

**Expect** (takes a couple of seconds):

```
  PASS header parses, checksum self-consistent
  PASS disassembles                              (12609 instructions from 12 entry points)
  SKIP reassembles byte-exact                    (GNU m68k binutils not installed)
  PASS patch writes only where told
  PASS checksum repaired after patching
  PASS expect guard rejects the wrong ROM
  PASS IPS patch reproduces the modified ROM
  PASS data map matches this ROM                 (112 fields, hash verified)
  PASS original ROM file untouched

8/9 checks passed, 1 skipped
```

The `SKIP` is expected on Windows and is fine — see
[Optional: the last check](#optional-the-last-check) at the end.

Any `FAIL` means stop and read it; each one names what went wrong.

> **`no such map file`?** You're in the wrong folder. Map paths are
> relative to `toolkit`. Either `cd` there or give the full path.

---

## Step 4 — Look at what you can edit

```
genesis-toolkit map-list nhl94.md maps\nhl94-ue.json
```

That prints all 112 mapped fields. Narrow it down:

```
genesis-toolkit map-list nhl94.md maps\nhl94-ue.json --filter TOR
```

**Expect:**

```
  team.TOR.city         0x0047ec  str  'Toronto'
  team.TOR.abbr         0x0047f6  str  'TOR'
  team.TOR.nickname     0x0047fc  str  'Maple Leafs'
  team.TOR.arena        0x00480a  str  'Maple Leaf Gardens'
```

All 28 teams are mapped — 26 NHL clubs plus both All-Star squads.

---

## Step 5 — Make your first mod

Start with something **you can see on screen**. A team name is ideal:
if it shows up in game, the offsets, the patch, the checksum repair and
the boot path are all confirmed at once.

```
genesis-toolkit map-set nhl94.md maps\nhl94-ue.json mymod.json --set "team.TOR.nickname=Blue Jays"
```

**Expect:**

```
  0x0047fc  4d61706c65204c656166 -> 426c7565204a61797300   team.TOR.nickname = Blue Jays
Wrote mymod.json (1 edit(s)). Apply it with:
  genesis-toolkit patch nhl94.md mymod.json modded.md
```

Open `mymod.json` in Notepad — it's small and readable. The `expect`
field records the bytes that were there before, so the mod refuses to
apply to the wrong ROM.

Now build the ROM:

```
genesis-toolkit patch nhl94.md mymod.json modded.md
```

**Expect:** `Bytes changed : 12` and `Wrote : modded.md`.

**Check it worked:**

```
genesis-toolkit map-list modded.md maps\nhl94-ue.json --filter TOR
```

You'll see `'Blue Jays'`, plus a warning that the ROM's hash no longer
matches the map. **That warning is correct** — you just changed the ROM.

> **Name too long?** Each string sits in a fixed slot and can't grow.
> `map-list` shows you the space available. Pick something shorter.

---

## Step 6 — Play it

Load `modded.md` in a Genesis emulator. Any of these work:

- **BizHawk** — best if you want the RAM search tools later
- **Genesis Plus GX** (standalone, or as a RetroArch core)
- **BlastEm** — best debugger
- **Gens r57shell mod** — the classic ROM-hacking build

Start an exhibition game, pick Toronto, and look at the team name.

**If you see "Blue Jays", the whole pipeline works** — disassembly,
mapping, patching, checksum, boot.

> **Full disclosure:** this is the one step I could never test for you.
> I have no emulator, so everything above is verified at the byte level
> and nothing is verified at the "it boots" level. If it fails here,
> that's genuinely new information — not something I checked and
> glossed over.

---

## Step 7 — Share it as a patch

Don't send people a modified ROM. Send an IPS patch — it carries only
your changes:

```
genesis-toolkit ips-create nhl94.md modded.md mymod.ips
```

A rename produces a patch of a few dozen bytes. Anyone with their own
copy of the ROM applies it with `ips-apply`, or any standard patcher.

---

## Where to go next

**Editing gameplay values** — speed, scoring, period length — means
finding them first, since they aren't text you can search for:

1. In BizHawk, use **RAM Search** while playing. Let the value change,
   re-search, filter until a couple of addresses remain.
2. Set a **breakpoint on write** to that address. Play until it trips.
3. Note the **PC** where it stopped — that's a ROM code address.
4. Cross-reference it:
   ```
   genesis-toolkit consts nhl94.md 5 --mnemonic cmp
   ```
   That lists every instruction comparing against 5 — a candidate set
   for something like period length.
5. Add it to a data map and it's a named field from then on, editable
   with `map-set` like any team name.

`consts` only sees the ~4.6% of the ROM the disassembler currently
reaches, so treat its output as candidates, not answers. Always confirm
with a breakpoint before editing.

---

## Optional: the last check

To un-skip `reassembles byte-exact`, you need the GNU m68k assembler,
which has no plain-Windows build. Install
[WSL](https://learn.microsoft.com/en-us/windows/wsl/install), then
inside it:

```
sudo apt install binutils-m68k-linux-gnu
pip install -e .
genesis-toolkit selftest nhl94.md --map maps/nhl94-ue.json
```

All 9 checks should pass. This unlocks `build`, `verify`, and mods
written as assembly rather than raw bytes.

**You do not need this for normal modding.** Eleven of the thirteen
commands — including everything in this guide — are pure Python.

---

## When something goes wrong

| Message | What it means |
|---|---|
| `no such file: nhl94.md` | Wrong folder, or the ROM isn't named that. `dir` to check. |
| `no such map file` | Map paths are relative to `toolkit`. `cd` there or use a full path. |
| `expected ... but found ...` | The mod doesn't match this ROM — often it was already applied. Start from a clean copy. |
| `needs N bytes but the slot is M` | The name is too long for its fixed slot. Shorten it. |
| `not recognized as an internal or external command` | Python isn't on PATH, or use `python -m genesis_toolkit.cli`. |
| `m68k-linux-gnu-as not found` | Only affects `build`/`verify`/asm edits. See above — everything else still works. |

Errors name the address and what was expected. That's deliberate: ROM
patching usually fails *silently*, and most of the engineering here went
into making it fail loudly instead.
