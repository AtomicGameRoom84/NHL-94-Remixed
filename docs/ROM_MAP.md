# ROM map — NHL '94 (USA, Europe)

Cartridge addresses. Every row cites how it was established; see
[FIDELITY.md](FIDELITY.md) for what the strength labels mean.

Nothing here is carved into `src/regions.json` yet — these are the
starting leads, recorded so the work does not begin from zero.

## Published by others

From KanedaFr's write-up, [gendev.spritesmind.net/page-nhl94.html](https://gendev.spritesmind.net/page-nhl94.html),
produced with IDA and the M.IDA loader script:

| Address | What | Strength |
| --- | --- | --- |
| `0x01A470` | Joypad read routine — identified by its port-write pattern | published |
| `0x01A430` | Branches into a block at `0x01A498` | published |
| `0x01A49A`–`0x01A4AE` | The original 3-button read (only 0x14 bytes) | published |
| `0x0F6D5E` | Multitap detector; writes DATA2 and CTRL2 | published |
| `0x011A78` | Jumps through the table at `0x011AF4` (nine routine pointers) | published |
| `0x011B92` | `jsr` target followed by data IDA misreads as code | published |
| `0x0FFB10` | End of useful data; padding beyond | published |

All three joypad routines reference DATA1 at `0xA10003`, which is the
controller port, not a ROM address.

## Established by reading the code

Found by this project's dispatch tracer (`toolkit/genesis_toolkit/tables.py`),
which recovers a table's base address from the instruction that loads it:

| Address | Entries | Form | Strength |
| --- | --- | --- | --- |
| `0x011AF4` | 9 | absolute longwords | named by an instruction |
| `0x0117B2` | 16 | signed word offsets from the base | named by an instruction |
| `0x018D7C` | 36 | absolute longwords | named by an instruction |
| `0x01A60A` | 8 | signed word offsets from the base | named by an instruction |

`0x011AF4` is the same table KanedaFr found by hand, with the same entry
count — an independent confirmation from a different method.

The two forms are encoded differently and must not be confused:

```
movea.l #$18d7c, a0          lea      $117b2(pc), a2
movea.l (a0,d1.w), a0        move.w   (a2,d0.w), d0
jsr     (a0)                 jsr      (a2,d0.w)

absolute longword addresses  signed 16-bit offsets from the base
```

The width comes from the *reader* instruction's size suffix. Reading a
word-offset table as longwords points into the vector table.

### Dispatch sites that cannot be resolved statically

Six sites load their target from RAM (`movea.l $cf24.w,a0`), through a
memory chain (`movea.l (a0),a0`), or off the stack (`movea.l (a7)+,a1`).
Those addresses exist only at runtime. They need a code/data log, not a
cleverer static pass.

## Team data

28 teams, `0x000646`–`0x005572`. Record format is
`[size byte][text][NUL][padding]`, where the trailing bytes are the next
record's size prefix — so a field must be written as text plus NUL and
never blank-padded.

Four fields per team (city, abbreviation, nickname, arena) are mapped by
name in `toolkit/maps/nhl94-ue.json`, 112 in total, read and written by
`genesis-toolkit map-list` / `map-set`.

| Team | City | Abbr | Nickname | Arena |
| --- | --- | --- | --- | --- |
| BOS | `0x000C28` | `0x000C30` | `0x000C36` | `0x000C3E` |

The remaining 27 follow the same four-field shape; see the map file for
every offset.

## Header

Standard Genesis cartridge header at `0x000100`–`0x0001FF`. Serial
`GM T-50406-00`. Declared ROM end at `0x0001A4`, which is what the
checksum at `0x00018E` covers — the sum of big-endian words from
`0x000200` to that declared end, not to the end of the file.
