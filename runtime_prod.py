import struct
from collections.abc import Sequence

from unicorn.unicorn import Uc
from unicorn.x86_const import (
    UC_X86_REG_GS_BASE,
    UC_X86_REG_R8,
    UC_X86_REG_R9,
    UC_X86_REG_RCX,
    UC_X86_REG_RDX,
    UC_X86_REG_RSP,
)

from unicorn import UC_PROT_ALL

from unplayplay.consts import MEM
from unplayplay.emu.addressing import align

# unplayplay default 8 MiB; deeper stacks help 1.2.88+ paths. Cap at 16 MiB so [stack) ends at
# MEM.HEAP_ADDR (0x2000000) and does not overlap the emulated heap.
_STACK_SIZE = min(max(align(MEM.STACK_SIZE), 0x1000000), MEM.HEAP_ADDR - MEM.STACK_ADDR)

def setup_stack(mu: Uc):
    mu.mem_map(MEM.STACK_ADDR, _STACK_SIZE, UC_PROT_ALL)
    mu.reg_write(UC_X86_REG_RSP, MEM.STACK_ADDR + _STACK_SIZE)

def setup_teb(mu: Uc):
    mu.mem_map(MEM.TEB_ADDR, MEM.PAGE_SIZE * 2) # Map 2 pages for TEB + PEB
    peb_addr = MEM.TEB_ADDR + MEM.PAGE_SIZE

    stack_base = MEM.STACK_ADDR + _STACK_SIZE
    stack_limit = MEM.STACK_ADDR
    
    # x64 TEB: Offset 0x00 is NtTib, Offset 0x30 is Self, Offset 0x60 is PEB
    teb_data = struct.pack("<QQQ", 0, stack_base, stack_limit)
    mu.mem_write(MEM.TEB_ADDR, teb_data)
    mu.mem_write(MEM.TEB_ADDR + 0x30, struct.pack("<Q", MEM.TEB_ADDR))
    mu.mem_write(MEM.TEB_ADDR + 0x60, struct.pack("<Q", peb_addr))
    
    # x64 PEB: Offset 0x02 is BeingDebugged (set to 0)
    mu.mem_write(peb_addr, b"\x00" * 0x100)
    
    mu.reg_write(UC_X86_REG_GS_BASE, MEM.TEB_ADDR)

def emulate_call(mu: Uc, func: int, args: Sequence[int]):
    original_rsp = mu.reg_read(UC_X86_REG_RSP)
    rsp = mu.reg_read(UC_X86_REG_RSP)
    rsp -= 0x20
    rsp -= 8
    mu.mem_write(rsp, struct.pack("<Q", MEM.EXIT_ADDR))
    mu.reg_write(UC_X86_REG_RSP, rsp)
    regs = [UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9]
    for index, arg in enumerate(args[:4]):
        mu.reg_write(regs[index], arg)
    mu.emu_start(func, MEM.EXIT_ADDR)
    mu.reg_write(UC_X86_REG_RSP, original_rsp)
