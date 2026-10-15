"""Package the verified local debug preview with adjacent DLLs and Resources."""
import hashlib
import json
import zipfile
from pathlib import Path
from verify_windows_content import main as verify

ROOT=Path(__file__).resolve().parents[1]


def main():
    verify()
    base=ROOT/'legacy/cocos-poc/build/windows-model/proj/Debug'
    out=ROOT/'runtime/dist'
    out.mkdir(parents=True,exist_ok=True)
    audit=json.loads((ROOT/'analysis/cocos-native-model/content-verification.json').read_text('utf8'))
    files=sorted([base/'hczs-cocos-poc.exe',*base.glob('*.dll'),*(p for p in (base/'Resources').rglob('*') if p.is_file())])
    records=[]
    for path in files:
        with path.open('rb') as stream:
            records.append(dict(path=path.relative_to(base).as_posix(),bytes=path.stat().st_size,sha256=hashlib.file_digest(stream,'sha256').hexdigest()))
    identity=hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest()[:12]
    destination=out/f'hczs-windows-x64-preview-{identity}.zip'
    instructions=('黑潮之上本地重建预览（Windows x64 调试构建）\n\n'
        '请完整解压，保持 DLL 和 Resources 与 hczs-cocos-poc.exe 在同一目录，再启动程序。\n'
        '此包仅包含客户端；本地 Node.js 预览服务需要另行启动。服务器连接地址请以客户端设置为准。\n'
        '包含从原始 APK 恢复的资源及重建战斗逻辑，不是完整原版游戏。\n'
        '本次只验证构建与文件一致性，未完成此版本的 Windows 画面及输入验收。\n')
    with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in files:
            archive.write(path,'hczs-preview/'+path.relative_to(base).as_posix())
        archive.writestr('hczs-preview/README.txt',instructions.encode('utf-8-sig'))
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP integrity failure')
        for row in records:
            if hashlib.sha256(archive.read('hczs-preview/'+row['path'])).hexdigest()!=row['sha256']:
                raise ValueError('Packaged file mismatch: '+row['path'])
    with destination.open('rb') as stream:
        checksum=hashlib.file_digest(stream,'sha256').hexdigest()
    report=dict(path=str(destination),bytes=destination.stat().st_size,sha256=checksum,files=records,
        executable=audit['executable'],crc_verified=True,all_file_hashes_verified=True,runtime_verified=False,
        scope='Debug client and adjacent dependencies; server separate; no clean-machine or gameplay verification')
    (ROOT/'analysis/cocos-native-model/package-verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({k:report[k] for k in ('path','bytes','sha256')}))


if __name__=='__main__':
    main()
