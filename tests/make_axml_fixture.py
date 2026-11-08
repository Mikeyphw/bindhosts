#!/usr/bin/env python3
"""Synthetic Android binary manifests (not real apps) for parser and CLI tests."""
import pathlib
import struct
import sys
import zipfile

S = [
    'manifest', 'application', 'service', 'receiver', 'provider', 'activity',
    'activity-alias', 'package', 'name', 'enabled',
    'http://schemas.android.com/apk/res/android',
    'com.example.app', 'com.google.android.gms.measurement.AppMeasurementService',
    '.AppReceiver', 'com.facebook.appevents.AppEventsReceiver',
    'com.google.firebase.provider.FirebaseInitProvider', '.MainActivity',
    'com.adjust.sdk.AdjustReceiver', 'com.example.app.SecondaryActivity',
]
N = {x: i for i, x in enumerate(S)}
NO = 0xFFFFFFFF

def hdr(t, h, payload):
    return struct.pack('<HHI', t, h, 8 + len(payload)) + payload

def utf8_size(n):
    return bytes([n]) if n <= 127 else bytes([(n >> 8) | 0x80, n & 0xFF])

def string_pool(utf8):
    offsets = []
    raw = bytearray()
    for s in S:
        offsets.append(len(raw))
        if utf8:
            raw += utf8_size(len(s)) + utf8_size(len(s.encode())) + s.encode() + b'\x00'
        else:
            raw += struct.pack('<H', len(s)) + s.encode('utf-16le') + b'\x00\x00'
    while len(raw) % 4:
        raw.append(0)
    header_size = 28
    starts_at = header_size + len(S) * 4
    return hdr(0x0001, header_size, struct.pack('<IIIII',len(S),0,0x100 if utf8 else 0,starts_at,0)
        + struct.pack('<'+'I'*len(S),*offsets) + raw)

def attr(name, value, android=False, boolean=None):
    ns = N['http://schemas.android.com/apk/res/android'] if android else NO
    if boolean is None:
        return struct.pack('<IIIHBBI',ns,N[name],N[value],8,0,3,N[value])
    return struct.pack('<IIIHBBI',ns,N[name],NO,8,0,0x12,int(boolean))

def start(name, attrs=()):
    return hdr(0x0102,16, struct.pack('<II',1,NO) + struct.pack('<IIHHHHHH',NO,N[name],20,20,len(attrs),0,0,0)
        + b''.join(attrs))

def end(name):
    return hdr(0x0103,16,struct.pack('<IIII',1,NO,NO,N[name]))

def make(utf8=True):
    chunks = [string_pool(utf8),
       start('manifest',[attr('package','com.example.app')]),
       start('application'),
       start('service',[attr('name','com.google.android.gms.measurement.AppMeasurementService',True)]),end('service'),
       start('receiver',[attr('name','com.facebook.appevents.AppEventsReceiver',True)]),end('receiver'),
       start('receiver',[attr('name','com.adjust.sdk.AdjustReceiver',True),attr('enabled','name',True,boolean=False)]),end('receiver'),
       start('provider',[attr('name','com.google.firebase.provider.FirebaseInitProvider',True)]),end('provider'),
       start('activity',[attr('name','.MainActivity',True)]),end('activity'),
       start('activity-alias',[attr('name','com.example.app.SecondaryActivity',True)]),end('activity-alias'),
       end('application'),end('manifest')]
    body = b''.join(chunks)
    return struct.pack('<HHI',0x0003,8,len(body)+8)+body

if __name__ == '__main__':
    d=pathlib.Path(sys.argv[1]); d.mkdir(parents=True,exist_ok=True)
    for enc in ('utf8','utf16'):
        b=make(enc=='utf8')
        (d/f'manifest-{enc}.axml').write_bytes(b)
        with zipfile.ZipFile(d/f'app-{enc}.apk','w') as z:
            z.writestr('AndroidManifest.xml',b)
    (d/'truncated.axml').write_bytes(make()[:-9])
    (d/'garbage.axml').write_bytes(b'not xml!')
