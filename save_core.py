"""WorldApart A1SV v1 codec. Unedited MessagePack bytes remain byte-identical."""
import os
import math
import struct
import hashlib
import hmac
import json
import shutil
import tempfile
import uuid
from pathlib import Path
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

DEFAULT_ROOT = Path.home() / 'AppData/LocalLow/Nuverse/WorldApart/StorageV1'
ENC_KEY = bytes.fromhex('eb972713304f73f1d06ff79304dc0048939a957250689a6937de9d1b60c77b9b')
MAC_KEY = bytes.fromhex('67d92255f828454fb0176fc3262c47d56c77b070af57ae9f06b374ca883e10bd')

def decrypt(data):
    if data[:6] != b'A1SV\x01\x01':
        raise ValueError('不支持的存档封装或版本，未进行修改。')
    if len(data) < 70 or (len(data) - 54) % 16:
        raise ValueError('存档长度不正确，文件可能损坏。')
    if not hmac.compare_digest(hmac.digest(MAC_KEY, data[:-32], 'sha256'), data[-32:]):
        raise ValueError('存档完整性校验失败，文件可能损坏或游戏已更新加密密钥。')
    return unpad(AES.new(ENC_KEY, AES.MODE_CBC, data[6:22]).decrypt(data[22:-32]), 16)

def encrypt(plain, iv=None):
    iv = iv or os.urandom(16)
    body = b'A1SV\x01\x01' + iv + AES.new(ENC_KEY, AES.MODE_CBC, iv).encrypt(pad(plain, 16))
    return body + hmac.digest(MAC_KEY, body, 'sha256')

class Node:
    __slots__ = ('start', 'end', 'value', 'kind', 'children', 'path', 'code')
    def __init__(self, start, code, path):
        self.start, self.code, self.path = start, code, path
        self.end = start
        self.value = None
        self.kind = 'null'
        self.children = []
    def child(self, key):
        for k, n in self.children:
            if k == key and type(k) is type(key):
                return n
        raise KeyError(key)
    def at(self, *path):
        n = self
        for key in path:
            n = n.child(key)
        return n

class Document:
    def __init__(self, data):
        self.data, self.pos, self.nodes, self.changes = data, 0, {}, {}
        self.root = self._read(())
        if self.pos != len(data):
            raise ValueError('存档含有未识别的尾部数据。')
    def _take(self, size):
        end = self.pos + size
        if end > len(self.data):
            raise ValueError('MessagePack 数据截断。')
        v = self.data[self.pos:end]
        self.pos = end
        return v
    def _number(self, fmt):
        return struct.unpack(fmt, self._take(struct.calcsize(fmt)))[0]
    def _read(self, path, key=False, depth=0):
        if depth > 160:
            raise ValueError('存档嵌套层数超出支持范围。')
        start = self.pos
        c = self._take(1)[0]
        n = Node(start, c, path)
        count = None
        if c <= 0x7f: n.kind, n.value = 'int', c
        elif c >= 0xe0: n.kind, n.value = 'int', c - 256
        elif 0xa0 <= c <= 0xbf: n.kind, n.value = 'str', self._take(c & 31).decode('utf-8')
        elif 0x80 <= c <= 0x8f: n.kind, count = 'map', c & 15
        elif 0x90 <= c <= 0x9f: n.kind, count = 'array', c & 15
        elif c == 0xc0: pass
        elif c in (0xc2, 0xc3): n.kind, n.value = 'bool', c == 0xc3
        elif c in (0xca, 0xcb): n.kind, n.value = 'float', self._number('>f' if c == 0xca else '>d')
        elif c in range(0xcc, 0xd4):
            n.kind, n.value = 'int', self._number({0xcc:'>B',0xcd:'>H',0xce:'>I',0xcf:'>Q',0xd0:'>b',0xd1:'>h',0xd2:'>i',0xd3:'>q'}[c])
        elif c in (0xd9,0xda,0xdb,0xc4,0xc5,0xc6):
            size = self._number({0xd9:'>B',0xda:'>H',0xdb:'>I',0xc4:'>B',0xc5:'>H',0xc6:'>I'}[c])
            n.value = self._take(size)
            n.kind = 'str' if c >= 0xd9 else 'binary'
            if n.kind == 'str': n.value = n.value.decode('utf-8')
        elif c in (0xdc,0xdd,0xde,0xdf):
            n.kind = 'array' if c <= 0xdd else 'map'
            count = self._number('>H' if c in (0xdc,0xde) else '>I')
        elif c in (0xc7,0xc8,0xc9,0xd4,0xd5,0xd6,0xd7,0xd8):
            size = self._number({0xc7:'>B',0xc8:'>H',0xc9:'>I'}[c]) if c <= 0xc9 else 2 ** (c - 0xd4)
            n.kind, n.value = 'extension', self._take(size + 1)
        else: raise ValueError('不支持的 MessagePack 类型：' + hex(c))
        if count is not None:
            if count > len(self.data) - self.pos:
                raise ValueError('无效的容器长度。')
            seen = set()
            for i in range(count):
                k = self._read((), True, depth+1).value if n.kind == 'map' else i
                if not isinstance(k,(str,int)) or isinstance(k,bool):
                    raise ValueError('不支持的映射键类型。')
                if (type(k),k) in seen: raise ValueError('存档包含重复键。')
                seen.add((type(k),k))
                n.children.append((k, self._read(path+(k,), key, depth+1)))
        n.end = self.pos
        if not key: self.nodes[path] = n
        return n
    def value(self, node):
        return self.changes.get(node.path, (node.value,None))[0]
    def stage(self, node, text):
        if node.kind == 'int':
            value = int(text.strip())
            if not -(2**63) <= value < 2**64: raise ValueError('整数超出 64 位范围。')
            # Game serializes most progression and inventory counts as Int32.
            if -(2**31) <= node.value < 2**31 and not -(2**31) <= value < 2**31:
                raise ValueError('此字段须在 32 位整数范围内。')
            if 0 <= value <= 127: encoded = bytes([value])
            elif -32 <= value < 0: encoded = bytes([value & 255])
            else:
                options = [(0xcc,'>B',0,255),(0xcd,'>H',0,65535),(0xce,'>I',0,2**32-1),(0xcf,'>Q',0,2**64-1)] if value >= 0 else [(0xd0,'>b',-128,127),(0xd1,'>h',-32768,32767),(0xd2,'>i',-2**31,2**31-1),(0xd3,'>q',-2**63,2**63-1)]
                c,fmt,_,_ = next(x for x in options if x[2] <= value <= x[3])
                encoded = bytes([c]) + struct.pack(fmt,value)
        elif node.kind == 'float':
            value = float(text.strip())
            if not math.isfinite(value): raise ValueError('不能使用 NaN 或无穷大。')
            fmt = '>f' if node.code == 0xca else '>d'
            encoded = bytes([node.code]) + struct.pack(fmt,value)
            value = struct.unpack(fmt,encoded[1:])[0]
            if not math.isfinite(value): raise ValueError('数值超出浮点数范围。')
        elif node.kind == 'bool':
            t = text.strip().lower()
            if t not in ('true','false','1','0','是','否'): raise ValueError('布尔值请填写 true 或 false。')
            value = t in ('true','1','是')
            encoded = b'\xc3' if value else b'\xc2'
        elif node.kind == 'str':
            value = text
            b = value.encode('utf-8')
            if len(b) > 1024*1024: raise ValueError('字符串过长。')
            encoded = (bytes([0xa0+len(b)]) if len(b)<32 else b'\xd9'+struct.pack('>B',len(b)) if len(b)<256 else b'\xda'+struct.pack('>H',len(b)) if len(b)<65536 else b'\xdb'+struct.pack('>I',len(b))) + b
        else: raise ValueError('此类型只读。请展开容器，选择具体数值。')
        if value == node.value: self.changes.pop(node.path,None)
        else: self.changes[node.path] = (value,encoded)
    def render(self):
        chunks, p = [], 0
        for path, (_,encoded) in sorted(self.changes.items(), key=lambda x:self.nodes[x[0]].start):
            n = self.nodes[path]
            chunks.extend((self.data[p:n.start],encoded))
            p = n.end
        chunks.append(self.data[p:])
        return b''.join(chunks)

def digest(b): return hashlib.sha256(b).hexdigest()

def atomic_write(path, data):
    fd, tmp = tempfile.mkstemp(prefix='.editor-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

class SaveSession:
    def __init__(self, slot):
        self.slot = Path(slot).resolve()
        self.original = {name:(self.slot/name).read_bytes() for name in ('gameworld.msgpack','meta.msgpack')}
        self.world = Document(decrypt(self.original['gameworld.msgpack']))
        self.meta = Document(decrypt(self.original['meta.msgpack']))
        self.world.root.at('playerModel')
    def unchanged(self):
        if any((self.slot/n).read_bytes() != data for n,data in self.original.items()):
            raise RuntimeError('存档已被游戏或云同步更新。请重新读取，再进行修改。')
    def backup(self, backup_root, reason):
        target = Path(backup_root) / (datetime.now().strftime('%Y%m%d-%H%M%S')+'_'+self.slot.name+'_'+uuid.uuid4().hex[:8])
        target.mkdir(parents=True)
        for n,data in self.original.items(): (target/n).write_bytes(data)
        manifest = {'slot':str(self.slot),'time':datetime.now().isoformat(timespec='seconds'),'reason':reason,'sha256':{n:digest(b) for n,b in self.original.items()}}
        (target/'backup.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        return target
    def save(self, backup_root):
        self.unchanged()
        if not self.world.changes: raise ValueError('没有待保存的修改。')
        name_path = ('playerModel','playerName')
        if name_path in self.world.changes:
            self.meta.stage(self.meta.root.at('characterName'),self.world.changes[name_path][0])
        else: self.meta.changes.clear()
        payload = {'gameworld.msgpack':encrypt(self.world.render()),'meta.msgpack':encrypt(self.meta.render()) if self.meta.changes else self.original['meta.msgpack']}
        for n,b in payload.items():
            expected = self.world if n.startswith('gameworld') else self.meta
            if decrypt(b) != expected.render(): raise RuntimeError('保存前验证失败。')
            Document(decrypt(b))
        backup = self.backup(backup_root,'保存修改前')
        self.unchanged()
        self._replace(payload)
        return backup
    def _replace(self, payload):
        written = []
        try:
            for n,b in payload.items():
                if b != self.original[n]:
                    atomic_write(self.slot/n,b); written.append(n)
            for n,b in payload.items():
                if (self.slot/n).read_bytes() != b: raise IOError('写入后校验失败。')
        except Exception as error:
            failures = []
            for n in written:
                try: atomic_write(self.slot/n,self.original[n])
                except Exception as rollback_error: failures.append(str(rollback_error))
            if failures: raise RuntimeError('写入失败且自动回滚未完成。请从备份目录恢复。'+str(failures)) from error
            raise
    def restore(self, backup, backup_root):
        self.unchanged()
        backup = Path(backup)
        manifest = json.loads((backup/'backup.json').read_text(encoding='utf-8'))
        if Path(manifest['slot']).resolve() != self.slot: raise ValueError('该备份不属于当前存档槽。')
        payload = {n:(backup/n).read_bytes() for n in self.original}
        for n,b in payload.items():
            if digest(b) != manifest['sha256'][n]: raise ValueError('备份完整性校验失败。')
            Document(decrypt(b))
        recovery = self.backup(backup_root,'恢复备份前')
        self.unchanged(); self._replace(payload)
        return recovery
