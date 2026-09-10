"""Rink Editor — a desktop window for modding a Genesis cartridge.

Everything here sits on top of the same tested pieces the command line
uses (`datamap`, `patch`, `header`), so the window is a front end and
not a second implementation that can drift.

Two ways to change a ROM:

- **Teams** — named fields from a data map, edited as text. Each name
  lives in a fixed slot, so the editor enforces the slot's budget rather
  than letting a long name run into the next record.
- **Patches** — an address and the bytes to write there, which is what a
  Game Genie does at runtime, except written permanently into the file.
  Anything you can express as "put these bytes at this address" works,
  including gameplay values you find yourself.

The ROM on disk is never modified: you open one and save a new file.
"""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import datamap as datamap_mod
from . import patch as patch_mod
from .header import parse_header

TITLE = "Rink Editor"
FIELD_ORDER = ["city", "abbr", "nickname", "arena"]
FIELD_LABELS = {"city": "City", "abbr": "Code",
                "nickname": "Nickname", "arena": "Arena"}


def _default_map_path() -> Path | None:
    """The bundled data map, whether running from source or frozen."""
    roots = [Path(__file__).resolve().parent.parent]
    if getattr(sys, "frozen", False):           # PyInstaller
        roots.insert(0, Path(sys._MEIPASS))     # type: ignore[attr-defined]
        roots.insert(1, Path(sys.executable).parent)
    for root in roots:
        candidate = root / "maps" / "nhl94-ue.json"
        if candidate.is_file():
            return candidate
    return None


class RinkEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(TITLE)
        self.geometry("980x680")
        self.minsize(760, 520)

        self.rom: bytearray | None = None
        self.rom_path: Path | None = None
        self.original: dict[str, dict[str, str]] = {}
        self.dmap: datamap_mod.DataMap | None = None
        self.entries: dict[tuple[str, str], ttk.Entry] = {}
        self.counters: dict[tuple[str, str], ttk.Label] = {}
        self.patches: list[tuple[int, bytes]] = []

        self._build_toolbar()
        self._build_tabs()
        self._build_status()
        self._load_map()
        self._refresh_state()

    # ---------- layout ----------
    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(10, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="Open ROM…", command=self.open_rom).pack(side="left")
        self.save_btn = ttk.Button(bar, text="Save modded ROM…",
                                   command=self.save_rom, state="disabled")
        self.save_btn.pack(side="left", padx=(8, 0))
        self.undo_btn = ttk.Button(bar, text="Undo all changes",
                                   command=self.undo_all, state="disabled")
        self.undo_btn.pack(side="left", padx=(8, 0))
        self.rom_label = ttk.Label(bar, text="No ROM loaded", foreground="#777")
        self.rom_label.pack(side="right")

    def _build_tabs(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self._build_teams_tab()
        self._build_patch_tab()
        self._build_info_tab()

    def _build_teams_tab(self):
        outer = ttk.Frame(self.nb)
        self.nb.add(outer, text="  Teams  ")
        canvas = tk.Canvas(outer, highlightthickness=0)
        bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.teams_frame = ttk.Frame(canvas)
        self.teams_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        window = canvas.create_window((0, 0), window=self.teams_frame, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(window, width=e.width))
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

        def wheel(event):
            step = -1 if getattr(event, "delta", 0) > 0 or event.num == 4 else 1
            canvas.yview_scroll(step, "units")
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            canvas.bind_all(seq, wheel)

    def _build_patch_tab(self):
        f = ttk.Frame(self.nb, padding=12)
        self.nb.add(f, text="  Patches  ")
        ttk.Label(f, justify="left", text=(
            "Write bytes straight into the cartridge — the same thing a Game Genie\n"
            "does, except saved permanently into the file.\n\n"
            "Address is where in the ROM to write. Bytes are what to put there,\n"
            "as hex pairs. Example:  address 0047FC   bytes 426C7565")
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))

        ttk.Label(f, text="Address (hex)").grid(row=1, column=0, sticky="w")
        self.addr_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.addr_var, width=14).grid(row=2, column=0, sticky="w")
        ttk.Label(f, text="Bytes (hex)").grid(row=1, column=1, sticky="w", padx=(10, 0))
        self.bytes_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.bytes_var, width=30).grid(row=2, column=1,
                                                                sticky="w", padx=(10, 0))
        ttk.Button(f, text="Add patch", command=self.add_patch).grid(row=2, column=2,
                                                                    sticky="w", padx=(10, 0))
        ttk.Button(f, text="Remove selected",
                   command=self.remove_patch).grid(row=2, column=3, sticky="w", padx=(6, 0))

        self.patch_list = tk.Listbox(f, height=14)
        self.patch_list.grid(row=3, column=0, columnspan=4, sticky="nsew", pady=(14, 0))
        f.rowconfigure(3, weight=1)
        for c in range(4):
            f.columnconfigure(c, weight=1 if c == 1 else 0)

    def _build_info_tab(self):
        f = ttk.Frame(self.nb, padding=12)
        self.nb.add(f, text="  ROM info  ")
        self.info = tk.Text(f, wrap="word", height=20, relief="flat")
        self.info.pack(fill="both", expand=True)
        self.info.configure(state="disabled")

    def _build_status(self):
        self.status = ttk.Label(self, text="Open a ROM to begin.",
                                relief="sunken", anchor="w", padding=(8, 4))
        self.status.pack(fill="x", side="bottom")

    # ---------- data ----------
    def _load_map(self):
        path = _default_map_path()
        if path is None:
            self._say("No data map found — the Teams tab needs maps/nhl94-ue.json "
                      "next to the program.")
            return
        try:
            self.dmap = datamap_mod.load_map(path)
        except patch_mod.PatchError as e:
            self._say(f"Couldn't read the data map: {e}")
            return
        self._build_team_rows()

    def _team_names(self):
        """Team codes in map order, with the fields each one has."""
        teams: dict[str, dict[str, datamap_mod.Field]] = {}
        for field in self.dmap.fields:
            parts = field.name.split(".")
            if len(parts) == 3 and parts[0] == "team":
                teams.setdefault(parts[1], {})[parts[2]] = field
        return teams

    def _build_team_rows(self):
        for child in self.teams_frame.winfo_children():
            child.destroy()
        self.entries.clear()
        self.counters.clear()

        for row, (abbr, fields) in enumerate(self._team_names().items()):
            box = ttk.LabelFrame(self.teams_frame, text=f" {abbr} ", padding=8)
            box.grid(row=row, column=0, sticky="ew", padx=8, pady=4)
            self.teams_frame.columnconfigure(0, weight=1)
            for col, key in enumerate(FIELD_ORDER):
                field = fields.get(key)
                if field is None:
                    continue
                cell = ttk.Frame(box)
                cell.grid(row=0, column=col, sticky="ew", padx=(0, 10))
                box.columnconfigure(col, weight=1)
                budget = field.size - 1
                ttk.Label(cell, text=f"{FIELD_LABELS[key]}  0x{field.address:06X}",
                          foreground="#777").pack(anchor="w")
                var = tk.StringVar()
                entry = ttk.Entry(cell, textvariable=var)
                entry.pack(fill="x")
                counter = ttk.Label(cell, text=f"0/{budget}", foreground="#777")
                counter.pack(anchor="e")
                entry.configure(state="disabled")
                self.entries[(abbr, key)] = entry
                self.counters[(abbr, key)] = counter
                var.trace_add("write",
                              lambda *_a, a=abbr, k=key: self._on_edit(a, k))
                entry.var = var          # keep a reference alive

    def _on_edit(self, abbr, key):
        entry = self.entries[(abbr, key)]
        field = self._team_names()[abbr][key]
        budget = field.size - 1
        text = entry.var.get()
        if len(text) > budget:           # hard stop at the slot's capacity
            entry.var.set(text[:budget])
            text = entry.var.get()
        self.counters[(abbr, key)].configure(text=f"{len(text)}/{budget}")
        self._refresh_state()

    def _changed_fields(self):
        out = []
        for (abbr, key), entry in self.entries.items():
            base = self.original.get(abbr, {}).get(key)
            if base is not None and entry.var.get() != base:
                out.append((abbr, key, entry.var.get()))
        return out

    def _refresh_state(self):
        n = len(self._changed_fields()) + len(self.patches)
        has_rom = self.rom is not None
        self.save_btn.configure(state="normal" if has_rom and n else "disabled")
        self.undo_btn.configure(state="normal" if has_rom and n else "disabled")
        if not has_rom:
            self.status.configure(text="Open a ROM to begin.")
        elif n == 0:
            self.status.configure(text="Loaded and unchanged.")
        else:
            self.status.configure(
                text=f"{n} change{'' if n == 1 else 's'} pending — "
                     f"use “Save modded ROM…” to write a new file.")

    def _say(self, text):
        self.status.configure(text=text)

    # ---------- actions ----------
    def open_rom(self):
        path = filedialog.askopenfilename(
            title="Open a Genesis ROM",
            filetypes=[("Genesis ROM", "*.md *.bin *.gen *.smd"), ("All files", "*.*")])
        if not path:
            return
        data = Path(path).read_bytes()
        if len(data) < 0x200 or bytes(data[0x100:0x104]) != b"SEGA":
            messagebox.showerror(
                TITLE, "That file isn't a Sega Genesis ROM — there's no 'SEGA' "
                       "marker in its header.")
            return
        self.rom = bytearray(data)
        self.rom_path = Path(path)
        self.patches.clear()
        self.patch_list.delete(0, "end")
        self._read_fields()
        self._show_info()
        self.rom_label.configure(text=self.rom_path.name, foreground="")
        self._refresh_state()

    def _read_fields(self):
        self.original.clear()
        if self.dmap is None:
            return
        rom = bytes(self.rom)
        for abbr, fields in self._team_names().items():
            self.original[abbr] = {}
            for key, field in fields.items():
                try:
                    value = datamap_mod.read_field(rom, field)
                except patch_mod.PatchError:
                    value = ""
                self.original[abbr][key] = value
                entry = self.entries.get((abbr, key))
                if entry is not None:
                    entry.configure(state="normal")
                    entry.var.set(value)

    def _show_info(self):
        h = parse_header(bytes(self.rom))
        lines = [
            f"File          {self.rom_path}",
            f"Size          {len(self.rom):,} bytes",
            "",
            f"Title         {h.domestic_title.strip()}",
            f"Overseas      {h.overseas_title.strip()}",
            f"Serial        {h.serial_number.strip()}",
            f"Region        {h.region_codes.strip()}",
            f"ROM range     0x{h.rom_start:06X} – 0x{h.rom_end:06X}",
            f"Checksum      declared 0x{h.declared_checksum:04X}, "
            f"computed 0x{h.computed_checksum:04X}"
            f"  ({'matches' if h.checksum_ok else 'MISMATCH'})",
            "",
            "The checksum is recomputed for you when you save, so an edited",
            "cartridge still looks intact to the console and to other tools.",
        ]
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")
        self.info.insert("1.0", "\n".join(lines))
        self.info.configure(state="disabled")

    def add_patch(self):
        if self.rom is None:
            messagebox.showinfo(TITLE, "Open a ROM first.")
            return
        raw_addr = self.addr_var.get().strip().replace("0x", "").replace("$", "")
        raw_bytes = self.bytes_var.get().strip().replace(" ", "").replace("0x", "")
        try:
            address = int(raw_addr, 16)
        except ValueError:
            messagebox.showerror(TITLE, f"“{self.addr_var.get()}” isn't a hex address.")
            return
        try:
            data = bytes.fromhex(raw_bytes)
        except ValueError:
            messagebox.showerror(
                TITLE, "Bytes must be hex pairs, like 4E71 or 42 6C 75 65.")
            return
        if not data:
            messagebox.showerror(TITLE, "Enter at least one byte to write.")
            return
        if address < 0 or address + len(data) > len(self.rom):
            messagebox.showerror(
                TITLE, f"0x{address:06X} + {len(data)} bytes runs past the end of this "
                       f"{len(self.rom):,}-byte ROM.")
            return
        self.patches.append((address, data))
        self.patch_list.insert(
            "end", f"0x{address:06X}   {data.hex().upper()}   "
                   f"(was {bytes(self.rom[address:address+len(data)]).hex().upper()})")
        self.addr_var.set("")
        self.bytes_var.set("")
        self._refresh_state()

    def remove_patch(self):
        for index in reversed(self.patch_list.curselection()):
            self.patch_list.delete(index)
            del self.patches[index]
        self._refresh_state()

    def undo_all(self):
        for abbr, fields in self.original.items():
            for key, value in fields.items():
                entry = self.entries.get((abbr, key))
                if entry is not None:
                    entry.var.set(value)
        self.patches.clear()
        self.patch_list.delete(0, "end")
        self._refresh_state()

    def save_rom(self):
        if self.rom is None:
            return
        edits = []
        if self.dmap is not None:
            teams = self._team_names()
            for abbr, key, value in self._changed_fields():
                field = teams[abbr][key]
                try:
                    data = datamap_mod.encode_field(field, value)
                except patch_mod.PatchError as e:
                    messagebox.showerror(TITLE, str(e))
                    return
                edits.append(patch_mod.Edit(
                    address=field.address, data=data,
                    expect=bytes(self.rom[field.address:field.address + len(data)]),
                    note=f"{abbr}.{key}"))
        for address, data in self.patches:
            edits.append(patch_mod.Edit(address=address, data=data,
                                        expect=None, note="patch"))
        try:
            out = patch_mod.apply_edits(bytes(self.rom), edits)
        except patch_mod.PatchError as e:
            messagebox.showerror(TITLE, str(e))
            return

        suggested = (self.rom_path.stem + " MODDED" + self.rom_path.suffix
                     if self.rom_path else "modded.md")
        path = filedialog.asksaveasfilename(
            title="Save modded ROM", initialfile=suggested,
            defaultextension=self.rom_path.suffix if self.rom_path else ".md",
            filetypes=[("Genesis ROM", "*.md *.bin *.gen"), ("All files", "*.*")])
        if not path:
            return
        Path(path).write_bytes(out)
        changed = sum(1 for a, b in zip(self.rom, out) if a != b)
        messagebox.showinfo(
            TITLE, f"Saved {Path(path).name}\n\n{changed} bytes changed "
                   f"(including the repaired checksum).\n\nOpen it in your emulator.")
        self._say(f"Saved {Path(path).name} — {changed} bytes changed.")


def main(argv=None) -> int:
    app = RinkEditor()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
