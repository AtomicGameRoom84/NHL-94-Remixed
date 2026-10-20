; Synthetic reset handler for the test cartridge. Every byte here was
; written for this test suite -- it is not derived from any game.
;
; This file exists to prove the carve mechanism: tools/split.py replaces
; the corresponding slice of the incbin blob with this assembly, and
; tools/verify.py then has to still reproduce the cartridge exactly.

reset_handler:
	move.l	#$100,d0
	tst.w	d0
	beq.b	reset_handler
	bsr.w	sub_418
	nop
	nop
	nop
	rts

	dc.w	0		; alignment gap ahead of the subroutine

sub_418:
	movem.l	d0-d1/a0-a1,-(sp)
	movem.l	(sp)+,d0-d1/a0-a1
	rts
