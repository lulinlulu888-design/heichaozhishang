"""Record the shipped parameter consumer and bounded upstream-name search."""
import hashlib,json
from pathlib import Path
from trace_first_encounter import inventory
from inspect_battle_rules import read_module,walk_codes,export
from inspect_neox_animation import save_json
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/characters/lynn/battle'

def main():
    rows=inventory();OUT.mkdir(parents=True,exist_ok=True)
    consumer=export(rows[618],['getCardParamList','getParamList'])
    selected=next(c for c in consumer['code_objects'] if c['constant_path']==[24,3])
    if selected['bytecode_sha256']!='d5ec5aef9bbb09a9dfe876f0c2e7c24829790c1d5779a7f97a35665a59bd92aa':
        raise ValueError('Reviewed parameter consumer changed')
    save_json(OUT/'parameter-consumer.json',consumer)
    terms=[b'diyActionData',b'SKILL_DIY_PARAMETER',b'SKILL_DIY_VALUE'];hits=[];checked=0;skips=[]
    for row in rows.values():
        if not row.get('decoded_sha256') or 'cdata' in row['filename']:continue
        raw=(ROOT/row['output']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row['decoded_sha256']:raise ValueError('Module changed')
        checked+=1
        if not any(t in raw for t in terms):continue
        try:module=read_module(row)
        except (ValueError,KeyError) as error:
            skips.append(dict(index=row['index'],reason=str(error)));continue
        for path,code in walk_codes(module):
            matched=sorted({t.decode() for t in terms if t in code['names'] or t in code['consts']})
            if matched:hits.append(dict(index=row['index'],filename=row['filename'],constant_path=list(path),name=code['name'].decode(),terms=matched))
    report=dict(evidence='Local static evidence; no original execution',checked_non_cdata_modules=checked,hits=hits,skips=skips,
        consumer=dict(module=618,constant_path=[24,3],source_lines=[188,211],
            rule='Iterate actionData.STORYLINE_PARAM; if diyActionData contains the same name, replace its value; append additional DIY-only keys afterwards.',
            override_bytecode_range=[76,131],additional_key_range=[256,349]),
        unresolved=['No writer of diyActionData identified by exact symbol search in decoded non-cdata scripts.',
            'Card SKILL_DIY_PARAMETER/VALUE to cardAction.diyActionData construction remains unproven.',
            'Do not assert card 430203 passes 430201 into state844 until the producer is recovered.',
            'This search cannot exclude dynamic attribute construction or missing server code.'])
    save_json(OUT/'parameter-boundary.json',report)
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
