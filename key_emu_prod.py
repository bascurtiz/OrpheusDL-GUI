import hashlib
import logging
import struct
from pathlib import Path

# SEH metadata for Spotify 1.2.88.472 (same client as cycyrild/another-unplayplay)
_ANOTHER_UP_DIR = Path(__file__).resolve().parent / "vendor" / "another_unplayplay"
_ANOTHER_UP_THROWINFO = _ANOTHER_UP_DIR / "throwinfo.json"
_ANOTHER_UP_RUNTIMEFN = _ANOTHER_UP_DIR / "runtimefunction.json"

from pefile import PE
from unicorn import (
    UC_ARCH_X86,
    UC_HOOK_CODE,
    UC_HOOK_BLOCK,
    UC_HOOK_MEM_READ,
    UC_HOOK_MEM_FETCH_UNMAPPED,
    UC_HOOK_MEM_READ_UNMAPPED,
    UC_HOOK_MEM_WRITE_UNMAPPED,
    UC_MODE_64,
    UC_PROT_ALL,
    UC_PROT_READ,
    UC_PROT_EXEC,
)
from unicorn.unicorn import Uc
from unicorn.x86_const import (
    UC_X86_REG_RAX,
    UC_X86_REG_RCX,
    UC_X86_REG_RDX,
    UC_X86_REG_RBX,
    UC_X86_REG_RSP,
    UC_X86_REG_RBP,
    UC_X86_REG_RSI,
    UC_X86_REG_RDI,
    UC_X86_REG_R8,
    UC_X86_REG_GS_BASE,
    UC_X86_REG_RIP,
)

from unplayplay.consts import (
    AES_KEY_HOOK,
    EMULATOR_SIZES,
    MEM,
    PATHS,
    RT_DATA,
    RT_FUNCTIONS,
    SP_CLT_SHA2,
    VM_CONSTANTS,
)
try:
    import runtime_prod as _runtime_prod
except ImportError:
    _runtime_prod = None
from unplayplay.emu import runtime as _runtime_stock
from unplayplay.emu.addressing import align, rebase
from unplayplay.emu.heap_allocator import HeapAllocator, HeapChunk
from unplayplay.emu.hooks.hook_malloc import hook_malloc
from unplayplay.emu.hooks.hook_stubs import apply_stubs
from unplayplay.emu_session import EmuSession
from unplayplay.exceptions import EmulationError, KeyExtractionError
from unplayplay.seh.seh_hook import seh_hook
from unplayplay.seh.state_builder import build_state

logger = logging.getLogger(__name__)

class KeyEmu:
    # Stable Stub Page Base for Symbolic Hooking
    STUB_PAGE_BASE = 0x7FFF0000

    def rebase(self, va: int) -> int:
        return rebase(self._image_base, va)

    def __init__(self, sp_client_path: Path) -> None:
        client_data = sp_client_path.read_bytes()
        sp_client_sha256 = hashlib.sha256(client_data)
        
        apr_22 = bytes.fromhex("1701B8D8649740EEB71F211E724731EBC919E897A3948D67189580DBF33AFE51")
        allowed_hashes = [SP_CLT_SHA2, apr_22]
        digest = sp_client_sha256.digest()
        if digest not in allowed_hashes:
            raise ValueError(f"Unexpected sp client: {sp_client_sha256.hexdigest().upper()}")

        self._pe = PE(data=client_data, fast_load=True)
        self._mapped_image = self._pe.get_memory_mapped_image()
        self._image_base = getattr(self._pe.OPTIONAL_HEADER, "ImageBase")
        if digest == apr_22 and isinstance(self._mapped_image, (bytes, bytearray)):
            # cycyrild/another-unplayplay uses len(mapped); SizeOfImage can differ by alignment
            self._image_size = align(len(self._mapped_image))
        else:
            self._image_size = align(self._pe.OPTIONAL_HEADER.SizeOfImage)

        if digest == apr_22:
            # Match cycyrild/another-unplayplay: minimal Uc session (no IAT/PEB/sweep) + vendor SEH json
            self._apr_22_minimal_session = True
            # 1.2.88.472: PyPI "unplayplay" targets 1.2.86. Use fixed VAs from cycyrild/another-unplayplay
            # (same DLL hash, SP_CLT_VERSION 1.2.88.472) — https://github.com/cycyrild/another-unplayplay
            self._vm_init_value = bytes.fromhex("e0d7a9de5c72f52ba8378c526592fc75")
            self._vm_runtime_init = self.rebase(0x00000001803E3520)
            self._vm_object_transform = self.rebase(0x00000001803E5580)
            self._aes_key_va = self.rebase(0x0000000180426371)
            self._runtime_context_va = self.rebase(0x000000018179DEE0)
            self._cxx_throw_exception_va = self.rebase(0x0000000181674D08)
        else:
            self._apr_22_minimal_session = False
            # unplayplay default (1.2.86.x) — pypi unplayplay consts
            self._vm_init_value = VM_CONSTANTS.INIT_VALUE
            self._vm_object_transform = self.rebase(RT_FUNCTIONS.VM_OBJECT_TRANSFORM_VA)
            self._vm_runtime_init = self.rebase(RT_FUNCTIONS.VM_RUNTIME_INIT_VA)
            self._aes_key_va = self.rebase(AES_KEY_HOOK.TRIGGER_RIP)
            self._runtime_context_va = self.rebase(RT_DATA.RUNTIME_CONTEXT_VA)
            self._cxx_throw_exception_va = self.rebase(RT_FUNCTIONS.CXX_THROW_EXCEPTION_VA)
        # 1.2.86 path expects RAX==0 after init; 1.2.88+ may return a pointer in RAX (see another-unplayplay)
        self._check_init_rax_zero = digest != apr_22
        if digest == apr_22 and _ANOTHER_UP_THROWINFO.is_file() and _ANOTHER_UP_RUNTIMEFN.is_file():
            # PyPI unplayplay generated/ is for 1.2.86; 1.2.88 needs another-unplayplay’s metadata
            self._throw_infos_path: Path = _ANOTHER_UP_THROWINFO
            self._runtime_functions_path: Path = _ANOTHER_UP_RUNTIMEFN
        else:
            self._throw_infos_path = PATHS.THROW_INFOS_JSON
            self._runtime_functions_path = PATHS.RUNTIME_FUNCTIONS_JSON

        self._seh_state = build_state(
            image_base=self._image_base,
            runtime_functions_path=self._runtime_functions_path,
            throw_infos_path=self._throw_infos_path,
        )

        self._vm_obj_blob: bytearray | None = None
        if self._apr_22_minimal_session:
            self._rt = _runtime_stock
        else:
            self._rt = _runtime_prod or _runtime_stock
        import threading
        self._lock = threading.Lock()


    def _create_session(self) -> EmuSession:
        with self._lock:
            mu = Uc(UC_ARCH_X86, UC_MODE_64)

            if self._apr_22_minimal_session:
                mu.mem_map(self._image_base, self._image_size)
            else:
                mu.mem_map(self._image_base, self._image_size, UC_PROT_ALL)
            mu.mem_write(self._image_base, self._mapped_image)

            heap = HeapAllocator.create(mu, MEM.HEAP_ADDR, MEM.HEAP_SIZE)
            apply_stubs(mu, self._image_base)
            hook_malloc(mu, self._image_base, heap)

            if not self._apr_22_minimal_session:
                # --- prod-only: IAT / PEB / libcef (breaks 1.2.88+ when combined with another-unplayplay VAs) ---
                mu.mem_map(self.STUB_PAGE_BASE, 0x1000, UC_PROT_READ | UC_PROT_EXEC)
                mu.mem_write(self.STUB_PAGE_BASE, b"\xC3" * 0x1000)

                libcef_base = self._image_base + 0x4000000
                mu.mem_map(libcef_base, 0x1000, UC_PROT_READ)
                mu.mem_write(libcef_base, b"MZ" + b"\x00" * 62 + b"libcef.dll")

                mu.mem_map(0x7FFE0000, 0x1000, UC_PROT_READ)
                mu.mem_write(0x7FFE0000, b"\x00" * 0x1000)

                heap_handle_base = 0x000007FFFF000000
                mu.mem_map(heap_handle_base, 0x10000, UC_PROT_ALL)
                heap_data = bytearray(0x10000)
                struct.pack_into("<I", heap_data, 0x10, 0xEEFFEEFF)
                struct.pack_into("<I", heap_data, 0x14, 0x00000002)
                mu.mem_write(heap_handle_base, bytes(heap_data))

                api_list = [
                    "GetProcessHeap", "HeapAlloc", "HeapFree", "HeapReAlloc",
                    "GetCurrentProcessId", "TlsAlloc",
                ]
                iat_mapping = {
                    0x1751178: 0,
                    0x17511B0: 1,
                    0x17511B8: 2,
                    0x17511C8: 3,
                    0x1751170: 4,
                    0x17511E0: 5,
                }

                def api_bridge_hook(uc, address, size, user_data):
                    api_index = user_data
                    api_name = api_list[api_index]
                    if api_name == "GetProcessHeap":
                        uc.reg_write(UC_X86_REG_RAX, heap_handle_base + 0x1000)
                    elif api_name in ["HeapAlloc", "HeapReAlloc"]:
                        dwBytes = uc.reg_read(UC_X86_REG_R8)
                        ptr = heap.alloc(dwBytes).ptr
                        uc.reg_write(UC_X86_REG_RAX, ptr)
                    elif api_name == "HeapFree":
                        uc.reg_write(UC_X86_REG_RAX, 1)
                    elif api_name == "GetCurrentProcessId":
                        uc.reg_write(UC_X86_REG_RAX, 0x1234)
                    elif api_name == "TlsAlloc":
                        uc.reg_write(UC_X86_REG_RAX, 0)

                for idx, (rva, api_idx) in enumerate(iat_mapping.items()):
                    stub_va = int(self.STUB_PAGE_BASE + (idx * 16))
                    mu.mem_write(int(self._image_base + rva), stub_va.to_bytes(8, "little"))
                    mu.hook_add(
                        UC_HOOK_CODE, api_bridge_hook, user_data=api_idx,
                        begin=stub_va, end=stub_va,
                    )

            self._rt.setup_stack(mu)
            self._rt.setup_teb(mu)

            if not self._apr_22_minimal_session:
                peb_addr = MEM.TEB_ADDR + MEM.PAGE_SIZE
                params_addr = peb_addr + 0x1000
                mu.mem_map(params_addr, 0x1000, UC_PROT_ALL)
                mu.mem_write(peb_addr + 0x20, params_addr.to_bytes(8, "little"))
                mu.mem_write(peb_addr + 2, b"\x00")
                mu.mem_write(peb_addr + 0xBC, struct.pack("<I", 0))

            vm_obj = heap.alloc(EMULATOR_SIZES.VM_OBJECT)
            vm_rt_context = heap.alloc(EMULATOR_SIZES.RT_CONTEXT)
            vm_init_value = heap.alloc(len(self._vm_init_value))
            vm_init_value.write(self._vm_init_value)

            session = EmuSession(
                mu=mu,
                vm_obj=vm_obj,
                obfuscated_key=heap.alloc(EMULATOR_SIZES.OBFUSCATED_KEY),
                init_value=vm_init_value,
                derived_key=heap.alloc(EMULATOR_SIZES.DERIVED_KEY),
                captured_aes_key=None,
            )

            mu.hook_add(UC_HOOK_CODE, seh_hook, self._seh_state,
                        begin=self._cxx_throw_exception_va,
                        end=self._cxx_throw_exception_va)

            mu.hook_add(UC_HOOK_CODE, self._hook_aes_key, session,
                        begin=self._aes_key_va, end=self._aes_key_va)

            if self._vm_obj_blob is None:
                self._init_runtime(mu, vm_obj, vm_rt_context)
                self._vm_obj_blob = session.vm_obj.read()
            else:
                vm_obj.write(bytes(self._vm_obj_blob))

            return session

    def _init_runtime(self, uc: Uc, vm_obj: HeapChunk, vm_rt_context: HeapChunk) -> None:
        data = b"\x00" * 8 + self._runtime_context_va.to_bytes(8, "little")
        vm_rt_context.write(data)

        if not self._apr_22_minimal_session:
            peb_addr = MEM.TEB_ADDR + MEM.PAGE_SIZE
            params_addr = peb_addr + 0x1000
            try:
                uc.mem_map(0x597F000000000, 0x4000000, UC_PROT_ALL)
                uc.mem_map(0x59FF000000000, 0x4000000, UC_PROT_ALL)
            except OSError:
                pass

            def hook_sweep_bypass(uc, address, size, user_data):
                target_va = self._image_base + 0x16BF752
                uc.reg_write(UC_X86_REG_RIP, target_va)
                uc.reg_write(UC_X86_REG_RAX, 0)

            sweep_va = self._image_base + 0x16BF660
            uc.hook_add(UC_HOOK_CODE, hook_sweep_bypass, begin=sweep_va, end=sweep_va)

            def hook_call_site(uc, address, size, user_data):
                rdx = uc.reg_read(UC_X86_REG_RDX)
                if rdx == 0:
                    uc.reg_write(UC_X86_REG_RDX, params_addr)

            call_site_va = self._image_base + 0x16BF20D
            uc.hook_add(UC_HOOK_CODE, hook_call_site, begin=call_site_va, end=call_site_va)
            uc.reg_write(UC_X86_REG_GS_BASE, MEM.TEB_ADDR)

        try:
            self._rt.emulate_call(
                uc, self._vm_runtime_init, [vm_obj.ptr, vm_rt_context.ptr, 1]
            )
            if self._check_init_rax_zero:
                rax = uc.reg_read(UC_X86_REG_RAX)
                if rax != 0:
                    raise EmulationError(
                        f"VM initialization failed with status {hex(rax)}"
                    )
        except EmulationError:
            raise
        except Exception as e:
            raise EmulationError("Failed to initialize vm runtime") from e

    @staticmethod
    def _hook_aes_key(mu: Uc, address: int, size: int, session: EmuSession) -> None:
        rdx = mu.reg_read(UC_X86_REG_RDX)
        session.captured_aes_key = mu.mem_read(rdx, EMULATOR_SIZES.KEY)
        mu.emu_stop()

    def get_aes_key(self, obfuscated_key: bytes, content_id: bytes = b"") -> bytearray:
        _ = content_id 
        session = self._create_session()
        session.obfuscated_key.write(obfuscated_key)
        try:
            self._rt.emulate_call(session.mu, self._vm_object_transform,
                                [session.vm_obj.ptr, session.obfuscated_key.ptr, 
                                 session.derived_key.ptr, session.init_value.ptr])
        except Exception as e:
            raise EmulationError("Emulation failed during AES key extraction") from e

        if session.captured_aes_key is None:
            raise KeyExtractionError("Failed to capture decrypted key")

        return session.captured_aes_key
