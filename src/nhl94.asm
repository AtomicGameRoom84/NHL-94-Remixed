; NHL '94 (USA, Europe) -- matching disassembly root.
;
; This file is deliberately almost empty. Everything it assembles comes
; from build/regions.inc, which tools/split.py generates from the
; cartridge you supply: data still to be understood arrives as incbin
; blobs, and each identified routine arrives as committed assembly.
;
; Assembled with vasmm68k_mot -no-opt. The flag is load-bearing: without
; it vasm relaxes move.l #1,d0 (203c00000001) to moveq (7001), and the
; rebuild stops matching the cartridge.

	org	0

	include	"regions.inc"
