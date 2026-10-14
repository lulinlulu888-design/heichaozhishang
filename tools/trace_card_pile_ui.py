"""Recover the shipped card-library entry; preserve empty legacy pile modules."""
import hashlib
import json
from pathlib import Path
import inspect_battle_rules as static
from inspect_battle_ui_layout import Reader
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/battle-ui/piles'


def main():
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=APK_SHA256:
            raise ValueError('APK identity changed')
    OUT.mkdir(parents=True,exist_ok=True)
    index=json.loads((static.SCRIPT/'index.json').read_text('utf8'))
    evidence=[]; layouts={}
    for name, filename, methods in (
        ('unused','ui\\ui_fight\\pile\\UnusedCardPile.py',()),
        ('used','ui\\ui_fight\\pile\\UsedCardPile.py',()),
        ('entry','ui\\ui_fight\\pile\\OtherCardPile.py',()),
        ('own','ui\\ui_fight\\OwnCardArea.py',('<module>','initComponents')),
        ('auto','ui_auto\\uires_FightPanel_FightNewPanel_btn_card.py',()),
        ('dialog','ui\\ui_fight\\pile\\FightCardsDialog.py',()),
        ('dialog-auto','ui_auto\\uires_paidui_listPaidui_FightCardsDialog.py',()),
        ('tabs-auto','ui_auto\\uires_Common_CardDeckTab.py',()),
        ('cards-auto','ui_auto\\uires_paidui_listPaidui_FightCardsArea.py',()),
        ('item-auto','ui_auto\\uires_paidui_listPaidui_CardDeckItem.py',()),
        ('char-tabs-auto','ui_auto\\uires_Common_CardDeckCharTab.py',()),
    ):
        row=next(r for r in index if r['filename']==filename)
        report=static.export(row,methods)
        (OUT/(name+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
        evidence.append(dict(name=name,module=row))
        if name=='auto' or name.endswith('-auto'):
            module=static.read_module(row)
            paths=[c.decode() for c in module['consts'] if isinstance(c,bytes) and c.endswith(b'.csb')]
            if len(paths)!=1:
                raise ValueError('ambiguous card button CSB')
            path=OUT/('btn_card.csb' if name=='auto' else name+'.csb')
            provenance=extract(apk,read_catalogue(apk),paths[0],path,APK_SHA256)
            reader=Reader(path.read_bytes());root=reader.scalar('I',0)
            if reader.string(reader.field(root,0))!='2.1.0.0':
                raise ValueError('unsupported CSB version')
            layout=dict(source=provenance,tree=reader.node(reader.pointer(reader.field(root,3))))
            layouts[name]=layout
    report=dict(apk_sha256=APK_SHA256,modules=evidence,layout=layouts['auto'],layouts=layouts,
                schema_sha256=hashlib.sha256((ROOT/'tools/reference/cocos2dx/CSParseBinary.fbs').read_bytes()).hexdigest(),
                parser_sha256=hashlib.sha256((ROOT/'tools/inspect_battle_ui_layout.py').read_bytes()).hexdigest(),
                limitations=['Static layout and script references, not original runtime UI.',
                             'Legacy unused/used pile module names do not prove implemented controls.',
                             'Runtime enablement, modal selection and timeline behavior not ported.'])
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(layouts=list(layouts),modules=len(evidence))))


if __name__=='__main__':
    main()
