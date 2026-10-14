"""Extract and parse the source hall CSB with the shared bounded UI reader."""
import json
from pathlib import Path
from export_elsa_model import extract
from neox_resource_paths import read_catalogue
from extract_texture_samples import APK_SHA256
from inspect_battle_ui_layout import Reader

ROOT=Path(__file__).resolve().parents[1]
def main():
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    out=ROOT/'analysis/hall';out.mkdir(parents=True,exist_ok=True)
    target=out/'HomeHallMain_ext.csb'
    source=extract(apk,read_catalogue(apk),'uires/HallMainPanel/NewHallPanel/HomeHallMain_ext.csb',target,APK_SHA256)
    reader=Reader(target.read_bytes());root=reader.scalar('I',0)
    version=reader.string(reader.field(root,0))
    if version!='2.1.0.0':raise ValueError('Hall CSB version changed')
    tree=reader.node(reader.pointer(reader.field(root,3)))
    report=dict(source=source,version=version,node_count=len(reader.seen),tree=tree,
        scope='Partial static CSB field reader; no runtime layout, timeline or nested ProjectNode expansion')
    (out/'ui-tree.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(nodes=report['node_count'],version=version)))

if __name__=='__main__':main()
