# RAM map — NHL '94 (USA, Europe)

Genesis work RAM is `0xFF0000`–`0xFFFFFF`, mirrored from `0xE00000`.

**Reading disassembly listings:** a 68000 short absolute operand like
`$c466.w` sign-extends, so it means `0xFFC466`. Most of this game's
state accesses look like that, and mistaking `$c466.w` for ROM address
`0x00C466` sends you to the wrong place entirely.

This is where gameplay values live — speed, scoring, period length. It
is the map worth building first if modding is the goal, because it needs
no decompilation at all.

| Address | What | Strength |
| --- | --- | --- |
| `0xFFC469` | Game clock | published — [Kodewerx tracing guide](https://www.kodewerx.org/forum/viewtopic.php?p=35048) |
| `0xFFC466` | Compared against 2 in several routines | **lead, unconfirmed** |

## The `0xFFC466` lead

`genesis-toolkit consts` found `cmpi.w #$2, $c466.w` at `0x007928`,
`0x007A34`, `0x007B6C`, and `0x00F746`. Three bytes below the known game
clock at `0xFFC469`, so plausibly the same game-state block — period
number is the obvious candidate for a value compared against 2.

That is a hypothesis, not a finding. Confirm it with a write breakpoint
before acting on it.

## How to extend this

1. Find the value with the emulator's RAM search while playing.
2. Break on writes to it to find the code that sets it.
3. Cross-reference with `genesis-toolkit consts rom.md <value>` to find
   the instructions using that immediate.
4. Record it here with its strength, and add it to a data map so it
   becomes a named field.

Not from the original game, listed only so they are not mistaken for it:
KanedaFr's 6-button hack adds long-press counters at `0xFFBF06`–`0xFFBF09`.
