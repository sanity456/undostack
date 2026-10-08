"""Windows fd-0 compatibility for genlayer-test 0.29.2; never deployed."""
import os
import sys
import tempfile

def install():
    if sys.platform != "win32":
        return
    from gltest.direct import loader
    from gltest.direct.vm import VMContext
    if getattr(loader, "_batch_a_compat", False):
        return
    def inject(vm):
        from genlayer.py import calldata
        from genlayer.py.types import Address
        def addr(x):
            return Address(x) if isinstance(x, bytes) else x
        payload = calldata.encode({"contract_address": addr(vm._contract_address),
            "sender_address": addr(vm.sender), "origin_address": addr(vm.origin),
            "stack": [], "value": vm._value, "datetime": vm._datetime,
            "is_init": False, "chain_id": vm._chain_id, "entry_kind": 0,
            "entry_data": b"", "entry_stage_data": None})
        fd, path = tempfile.mkstemp()
        try:
            os.write(fd, payload)
            os.lseek(fd, 0, os.SEEK_SET)
            vm._original_stdin_fd = os.dup(0)
            os.dup2(fd, 0)
            vm._batch_a_path = path
        finally:
            os.close(fd)
    original = VMContext._cleanup_after_deactivate
    def cleanup(vm):
        path = getattr(vm, "_batch_a_path", None)
        try:
            original(vm)
        finally:
            if path:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
                vm._batch_a_path = None
    loader._inject_message_to_fd0 = inject
    VMContext._cleanup_after_deactivate = cleanup
    loader._batch_a_compat = True
install()

