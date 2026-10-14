"""Offline legacy rotor decoder; target code is never executed.

Python port of CPython v2.3.7 Modules/rotormodule.c:
https://raw.githubusercontent.com/python/cpython/v2.3.7/Modules/rotormodule.c

Copyright 1994 by Lance Ellinghouse,
Cathedral City, California Republic, United States of America.
All Rights Reserved
Permission to use, copy, modify, and distribute this software and its
documentation for any purpose and without fee is hereby granted,
provided that the above copyright notice appear in all copies and that
both that copyright notice and this permission notice appear in
supporting documentation, and that the name of Lance Ellinghouse
not be used in advertising or publicity pertaining to distribution
of the software without specific, written prior permission.
LANCE ELLINGHOUSE DISCLAIMS ALL WARRANTIES WITH REGARD TO
THIS SOFTWARE, INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS, IN NO EVENT SHALL LANCE ELLINGHOUSE BE LIABLE FOR ANY SPECIAL,
INDIRECT OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING
FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION
WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
"""
import functools
import math

# Observed in libclient.so SHA256 54f7cfbc5c62c8ded1fec86d8aac5bae78a52548da56bd138278f8e1f38bc9ef
DN = b's9f32sbyiz7et'  # .text file offset/VA 0xec4ca4
DT = b'&vpoal-'       # .text file offset/VA 0xec4ce0
DF = b'^cl#z9l%"@698' # .text file offset/VA 0xec4d14
KEY = DN*5 + DT*6 + b'@' + (DT+DN+DF)*4 + b'#!' + DF*3 + b'^%'

def _short(x):
    return x - 65536 if x >= 32768 else x

@functools.lru_cache(maxsize=16)
def _initial(key, count):
    key = key.split(b'\x00')[0]
    a,b,c,d,e = 995,576,767,671,463
    for x in key:
        a = ((a<<3 | a>>13)+x)&65535
        b = ((b<<3 | b>>13)^x)&65535
        c = ((c<<3 | c>>13)-x)&65535
        d = (x-(d<<3 | d>>13))&65535
        e = ((e<<3 | e>>13)^~x)&65535
    seed = [_short(a),_short(b|1),_short(c)]
    def rand(n):
        # C truncates signed division toward zero; Python // does not.
        for i,(mul,div,sub,mod) in enumerate(((171,177,2,30269),(172,176,35,30307),(170,178,63,30323))):
            q = int(seed[i]/div)
            v = mul*(seed[i]-q*div) - sub*q
            seed[i] = v+mod if v < 0 else v
        term = seed[0]/30269.0 + seed[1]/30307.0 + seed[2]/30323.0
        value = term-math.floor(term)
        return int((0.0 if value >= 1 else value)*n)%n
    enc, dec, positions, advances = [],[],[],[]
    for _ in range(count):
        positions.append(rand(256)); advances.append(1+2*rand(128))
        er=list(range(256)); dr=list(range(256))
        for i in range(256,1,-1):
            q=rand(i); j=er[q]; er[q]=er[i-1]; er[i-1]=j; dr[j]=i-1
        dr[er[0]]=0
        enc.append(bytes(er)); dec.append(bytes(dr))
    return tuple(enc),tuple(dec),tuple(positions),tuple(advances)

def _crypt(data,key,count,decipher):
    if isinstance(key,str): key=key.encode('latin1')
    enc,dec,initial,advances=_initial(bytes(key),count)
    positions=list(initial); out=bytearray(len(data))
    order=range(count-1,-1,-1) if decipher else range(count)
    for j,c in enumerate(data):
        if decipher:
            for i in order: c=positions[i]^dec[i][c]
        else:
            for i in order: c=enc[i][positions[i]^c]
        out[j]=c
        for i in range(count):
            temp=positions[i]+advances[i]; positions[i]=temp&255
            if temp >= 256 and i < count-1: positions[i+1]=(positions[i+1]+1)&255
    return bytes(out)

def decrypt(data,key=KEY,count=6):
    """Reset the rotor, then decrypt bytes using legacy CPython rotor behavior."""
    return _crypt(data,key,count,True)

def encrypt(data,key=KEY,count=6):
    """Inverse provided only to check decoder round trips on synthetic inputs."""
    return _crypt(data,key,count,False)
