"""Bounded, no-follow extended attributes, including Apple's system Python."""
import base64
import ctypes
import errno
from functools import lru_cache
import os
import sys

MAX_XATTR_BYTES = 2 * 1024 * 1024


@lru_cache(maxsize=1)
def native():
    lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    lib.listxattr.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    lib.listxattr.restype = ctypes.c_ssize_t
    lib.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    lib.getxattr.restype = ctypes.c_ssize_t
    lib.acl_get_link_np.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.acl_get_link_np.restype = ctypes.c_void_p
    lib.acl_get_entry.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
    lib.acl_get_entry.restype = ctypes.c_int
    lib.acl_free.argtypes = [ctypes.c_void_p]
    lib.acl_free.restype = ctypes.c_int
    return lib


def xattrs(path):
    values, total = {}, 0
    if hasattr(os, 'listxattr'):
        for name in os.listxattr(path, follow_symlinks=False):
            data = os.getxattr(path, name, follow_symlinks=False)
            total += len(data)
            if total > MAX_XATTR_BYTES:
                raise ValueError('文件扩展属性超过 2 MiB，无法完整保存。')
            values[name] = base64.b64encode(data).decode('ascii')
    elif sys.platform == 'darwin':
        lib, name = native(), os.fsencode(path)
        length = lib.listxattr(name, None, 0, 1)
        if length < 0 or length > MAX_XATTR_BYTES:
            raise OSError(ctypes.get_errno(), '无法读取扩展属性列表')
        buffer = ctypes.create_string_buffer(length)
        if lib.listxattr(name, buffer, length, 1) != length:
            raise ValueError('读取期间扩展属性发生变化。')
        for key in buffer.raw.split(b'\0'):
            if not key:
                continue
            size = lib.getxattr(name, key, None, 0, 0, 1)
            if size < 0 or total + size > MAX_XATTR_BYTES:
                raise ValueError('无法完整读取文件扩展属性，或超过 2 MiB。')
            value = ctypes.create_string_buffer(size)
            if lib.getxattr(name, key, value, size, 0, 1) != size:
                raise ValueError('读取期间扩展属性发生变化。')
            total += size
            values[os.fsdecode(key)] = base64.b64encode(value.raw).decode('ascii')
    else:
        raise ValueError('此平台不能完整检查文件扩展属性。')
    return values


def restore_xattrs(path, values):
    current = xattrs(path)
    lib = native() if sys.platform == 'darwin' and not hasattr(os, 'setxattr') else None
    for name in set(current) - set(values):
        if lib:
            if lib.removexattr(os.fsencode(path), os.fsencode(name), 1):
                raise OSError(ctypes.get_errno(), '无法恢复扩展属性范围')
        else:
            os.removexattr(path, name, follow_symlinks=False)
    for name, encoded in values.items():
        data = base64.b64decode(encoded, validate=True)
        if lib:
            if lib.setxattr(os.fsencode(path), os.fsencode(name), data, len(data), 0, 1):
                raise OSError(ctypes.get_errno(), '无法恢复扩展属性')
        else:
            os.setxattr(path, name, data, follow_symlinks=False)
    if xattrs(path) != values:
        raise ValueError('扩展属性恢复读回不一致。')


def has_acl(path):
    if sys.platform == 'darwin':
        # Darwin SDK sys/acl.h: EXTENDED=0x100, FIRST_ENTRY=0.
        # acl_get_link_np does not follow the final symbolic link. A valid
        # empty ACL returns -1/EINVAL for its first entry (Darwin acl_get_entry).
        def identity(value):
            return (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        before = identity(os.lstat(path))
        lib = native()
        acl = lib.acl_get_link_np(os.fsencode(path), 0x100)
        if not acl:
            error = ctypes.get_errno()
            # APFS reports ENOENT for an absent extended ACL as well as a
            # missing path. Require an unchanged, existing no-follow identity.
            after = os.lstat(path)
            if before != identity(after):
                raise ValueError('ACL 检查期间路径发生变化。')
            if error == errno.ENOENT:
                return False
            raise OSError(error, '无法检查文件 ACL', str(path))
        try:
            entry = ctypes.c_void_p()
            ctypes.set_errno(0)
            result = lib.acl_get_entry(acl, 0, ctypes.byref(entry))
            if identity(os.lstat(path)) != before:
                raise ValueError('ACL 检查期间路径发生变化。')
            if result == 0:
                return True
            error = ctypes.get_errno()
            if result == -1 and error == errno.EINVAL:
                return False
            raise OSError(error, '无法读取文件 ACL 条目', str(path))
        finally:
            if lib.acl_free(acl):
                raise OSError(ctypes.get_errno(), '无法释放 ACL 读取结果')
    return any('posix_acl' in name for name in xattrs(path))
