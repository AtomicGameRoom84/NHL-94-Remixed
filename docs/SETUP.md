# Setup

## Linux / macOS

```sh
python3 tools/setup.py
cp "NHL '94 (USA, Europe).md" rom/nhl94.md
python3 tools/verify.py
```

Needs Python 3.11+, `make`, and a C compiler. `tools/setup.py` fetches
vasm against a pinned SHA-256, builds it, and installs it to
`.local/vasm/` — which is gitignored, so it never enters the repo.

## Windows

`tools/setup.py` builds vasm from C source, so it needs a toolchain.
Either:

**MSYS2/MinGW** — install it, then run the same commands from the MinGW
shell.

**Or skip the build.** Get a `vasmm68k_mot.exe` binary, put it on your
`PATH` (or pass `--assembler C:\path\to\vasmm68k_mot.exe`), and go
straight to `verify.py`. The pin in `tools/toolchain-lock.json` records
which version this project was tested against; a different one may
encode something differently, and `verify.py` will say so by failing.

Windows is untested — see [VERIFICATION.md](../VERIFICATION.md).

## Expected output

```
Cartridge   : nhl94-ue (NHL '94 (USA, Europe))
Regions     : 0 (0 bytes identified as code, 0.00%)
Rebuilt     : 1,048,576 bytes
BIT-PERFECT: the rebuild is the cartridge, byte for byte.
```

`Regions: 0` is correct for a fresh checkout. The whole cartridge is one
`incbin` until a region is proven.

## If it fails

**"is not a revision this project knows"** — your dump is a different
revision, a bad dump, or has a copier header. The error prints its SHA-1
and SHA-256; if it is a good dump you want supported, add those to
`tools/rom-lock.json`.

**"vasmm68k_mot not found"** — run `tools/setup.py`, or pass
`--assembler`.

**"BYTE MISMATCH"** on a fresh checkout with no regions — that should be
impossible and means the assembler is misbehaving. Check its version
against the pin, and confirm `-no-opt` is being passed.

## Tests

```sh
python3 -m pytest tests/ -q
```

Runs against a synthetic fixture cartridge, so it needs no ROM and works
in CI.
