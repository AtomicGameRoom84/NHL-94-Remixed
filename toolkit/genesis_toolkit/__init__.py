"""genesis_toolkit: a generic disassembly/reassembly toolkit for Sega
Genesis / Mega Drive ROMs.

Nothing in this package embeds or depends on any specific game's data.
Every tool here takes a ROM path as input and works on the standard
Genesis cartridge header + 68000 vector table format shared by all
Genesis/Mega Drive titles, so it is reusable across games, not just the
one it was first built against.
"""

__version__ = "0.1.0"
