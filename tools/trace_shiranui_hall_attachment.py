"""Pin the hall decoration lookup chain; static script evidence, no execution."""
import json
from pathlib import Path
from extract_game_data import export_table
from inspect_battle_rules import export

ROOT=Path(__file__).resolve().parents[1]
def main():
    rows=json.loads((ROOT/'analysis/assets/decoded/script/index.json').read_text('utf8'))
    evidence=[export(next(r for r in rows if r['index']==i),names) for i,names in
        [(418,('updateUserData',)),(5136,('getModelPathListByMeshIndexList','getModelPathByMeshIndex'))]]
    entity=export_table(1955,{71});decoration=export_table(9416,{191})
    if entity['rows'][0]['fields']['HOME_SUB_MODEL_LIST']!=[191]:raise ValueError('Home attachment list changed')
    if decoration['rows'][0]['fields']['MODEL']!='character/player/buzhihuo/buzhihuo_weapon.gim':raise ValueError('Decoration model changed')
    report=dict(entity=entity,decoration=decoration,consumer_evidence=evidence,
        observations=['HomeModelEntity.updateUserData maps EntityData.HOME_SUB_MODEL_LIST via MeshHelper.getModelPathListByMeshIndexList to SubModelPathList.',
            'MeshHelper.getModelPathByMeshIndex reads getDecorationTable, MODEL and LOD_NUM, not avatar_slave_table.',
            'Decoration191 has LOD_NUM=0, MODEL=buzhihuo_weapon.gim and an explicit spring configuration path.'],
        limits=['Static consumer chain only; original runtime component selection and attachment/timing not executed.',
            'Spring configuration and bound SFX have not been simulated.'])
    (ROOT/'analysis/characters/shiranui/hall-attachment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(entity=71,decoration=191,model=decoration['rows'][0]['fields']['MODEL'])))
if __name__=='__main__':main()
