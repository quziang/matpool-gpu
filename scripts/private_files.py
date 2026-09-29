"""Create private UTF-8 files without a moment of inherited Windows read access."""
import contextlib
import os
from pathlib import Path


@contextlib.contextmanager
def _windows_security(path):
    import ctypes as c
    from ctypes import wintypes as w

    kernel = c.WinDLL('kernel32', use_last_error=True)
    advapi = c.WinDLL('advapi32', use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.LocalFree.argtypes = [c.c_void_p]
    kernel.LocalFree.restype = c.c_void_p
    kernel.GetVolumePathNameW.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD]
    kernel.GetVolumeInformationW.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD,
        c.POINTER(w.DWORD), c.POINTER(w.DWORD), c.POINTER(w.DWORD), w.LPWSTR, w.DWORD]
    volume, flags = c.create_unicode_buffer(32768), w.DWORD()
    if not kernel.GetVolumePathNameW(str(Path(path).absolute()), volume, len(volume)):
        raise c.WinError(c.get_last_error())
    if not kernel.GetVolumeInformationW(volume, None, 0, None, None, c.byref(flags), None, 0):
        raise c.WinError(c.get_last_error())
    if not flags.value & 8:  # FILE_PERSISTENT_ACLS (FAT/exFAT cannot protect secrets)
        raise OSError('Private files require a volume supporting persistent ACLs.')
    advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)]
    advapi.GetTokenInformation.argtypes = [w.HANDLE, c.c_int, c.c_void_p,
                                           w.DWORD, c.POINTER(w.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes = [c.c_void_p, c.POINTER(w.LPWSTR)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        w.LPCWSTR, w.DWORD, c.POINTER(c.c_void_p), c.POINTER(w.DWORD)]

    class SecurityAttributes(c.Structure):
        _fields_ = [('nLength', w.DWORD), ('lpSecurityDescriptor', c.c_void_p),
                    ('bInheritHandle', w.BOOL)]

    token, sid, descriptor = w.HANDLE(), w.LPWSTR(), c.c_void_p()
    try:
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, c.byref(token)):
            raise c.WinError(c.get_last_error())
        size = w.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, c.byref(size))  # TokenUser
        if not size.value:
            raise c.WinError(c.get_last_error())
        data = c.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, data, size, c.byref(size)):
            raise c.WinError(c.get_last_error())
        user_sid = c.cast(data, c.POINTER(c.c_void_p))[0]
        if not advapi.ConvertSidToStringSidW(user_sid, c.byref(sid)):
            raise c.WinError(c.get_last_error())
        # Protected DACL: only the current process user; no inherited broad ACEs.
        if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                'D:P(A;;FA;;;' + sid.value + ')', 1, c.byref(descriptor), None):
            raise c.WinError(c.get_last_error())
        attributes = SecurityAttributes(c.sizeof(SecurityAttributes), descriptor, False)
        yield c, w, kernel, attributes
    finally:
        if descriptor.value:
            kernel.LocalFree(descriptor)
        if sid:
            kernel.LocalFree(c.cast(sid, c.c_void_p))
        if token.value:
            kernel.CloseHandle(token)


def make_private_directory(path):
    """Private leaf directory; callers validate existing paths before using them."""
    path = Path(path)
    if os.name != 'nt':
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with _windows_security(path) as (c, w, kernel, attributes):
        kernel.CreateDirectoryW.argtypes = [w.LPCWSTR, c.POINTER(type(attributes))]
        if not kernel.CreateDirectoryW(str(path.absolute()), c.byref(attributes)):
            error = c.get_last_error()
            if error != 183 or not path.is_dir():  # ERROR_ALREADY_EXISTS
                raise c.WinError(error)


def open_private_text(path):
    """Exclusive create; permissions applied at creation, before writing secrets.

    POSIX uses 0600. Windows uses a protected current-user DACL. Privileged
    administrators/backup operators remain outside this confidentiality boundary.
    Existing files are never opened or truncated. Parents must already exist.
    """
    if os.name != 'nt':
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    else:
        import msvcrt
        with _windows_security(path) as (c, w, kernel, attributes):
            kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD,
                c.POINTER(type(attributes)), w.DWORD, w.DWORD, w.HANDLE]
            kernel.CreateFileW.restype = w.HANDLE
            handle = kernel.CreateFileW(str(Path(path).absolute()), 0x40000000, 0,
                                       c.byref(attributes), 1, 0x80, None)
            if handle == c.c_void_p(-1).value:
                raise c.WinError(c.get_last_error())
            try:
                fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
            except BaseException:
                kernel.CloseHandle(handle)
                raise
    try:
        return os.fdopen(fd, 'w', encoding='utf-8', newline='\n')
    except BaseException:
        os.close(fd)
        raise
