"""Bounded, reproducible static inventory of the supplied game APK."""
from __future__ import annotations
import argparse, collections, hashlib, json, pathlib, re, struct, sys, zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
APK = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
OUT = ROOT / 'analysis' / 'assets'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--verify-filelist',action='store_true');ap.add_argument('--catalogue',action='store_true');args=ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(APK) as z, APK.open('rb') as src:
        rows=[]
        for i in z.infolist():
            src.seek(i.header_offset)
            local=src.read(30)
            name_len,extra_len=struct.unpack_from('<HH',local,26)
            rows.append(dict(name=i.filename,size=i.file_size,compressed_size=i.compress_size,compression=i.compress_type,crc32=f'{i.CRC:08x}',header_offset=i.header_offset,data_offset=i.header_offset+30+name_len+extra_len))
        (OUT/'members.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        ext=collections.defaultdict(lambda: [0,0]); dirs=collections.defaultdict(lambda:[0,0])
        for r in rows:
            suffix=pathlib.PurePosixPath(r['name']).suffix.lower() or '<none>'
            ext[suffix][0]+=1;ext[suffix][1]+=r['size']
            prefix='/'.join(r['name'].split('/')[:2])
            dirs[prefix][0]+=1;dirs[prefix][1]+=r['size']
        summary=dict(apk=str(APK),apk_size=APK.stat().st_size,member_count=len(rows),uncompressed_size=sum(r['size'] for r in rows),extensions=sorted([dict(ext=k,count=v[0],size=v[1]) for k,v in ext.items()],key=lambda r:-r['size']),directories=sorted([dict(path=k,count=v[0],size=v[1]) for k,v in dirs.items()],key=lambda r:-r['size']),largest=sorted(rows,key=lambda r:-r['size'])[:35])
        (OUT/'inventory.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:summary[k] for k in ('apk_size','member_count','uncompressed_size','extensions')},ensure_ascii=False,indent=2))
        if args.catalogue:
            catalogue=[]
            for member in z.infolist():
                if not member.filename.endswith('.npk'):continue
                with z.open(member) as f:
                    magic,count,r1,r2,version,index_offset=struct.unpack('<4s5I',f.read(24))
                    if magic!=b'NXPK' or index_offset+count*28!=member.file_size:raise ValueError('invalid NPK index')
                    f.seek(index_offset);idx=f.read(count*28)
                entries=[struct.unpack_from('<6I2H',idx,n*28) for n in range(count)]
                if any(r[1]<24 or r[1]+r[2]>index_offset for r in entries):raise ValueError('invalid NPK entry bounds')
                catalogue.append(dict(member=member.filename,count=count,index_offset=index_offset,index_sha256=hashlib.sha256(idx).hexdigest(),stored_size=member.file_size,original_size=sum(r[3] for r in entries),flags=dict(collections.Counter(str(r[6:]) for r in entries))))
            (OUT/'npk_catalogue.json').write_text(json.dumps(catalogue,indent=2),encoding='utf-8')
            print('NPK catalogue:',len(catalogue),'packs;',sum(r['count'] for r in catalogue),'entries')
        if args.verify_filelist:
            manifest=z.read('assets/filelist.txt');checks=[]
            for line in manifest.decode('utf-8').splitlines():
                name,expected=line.split('\t');name='assets/'+name
                if name not in z.namelist():checks.append(dict(name=name,status='missing'));continue
                md5=hashlib.md5();sha256=hashlib.sha256()
                with z.open(name) as f:
                    for block in iter(lambda:f.read(1024*1024),b''):md5.update(block);sha256.update(block)
                checks.append(dict(name=name,expected_md5=expected,actual_md5=md5.hexdigest(),sha256=sha256.hexdigest(),status='match' if md5.hexdigest()==expected else 'mismatch'))
            report=dict(manifest_sha256=hashlib.sha256(manifest).hexdigest(),counts=dict(collections.Counter(r['status'] for r in checks)),checks=checks)
            (OUT/'filelist_verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('Filelist verification:',report['counts'])

if __name__ == '__main__': main()
