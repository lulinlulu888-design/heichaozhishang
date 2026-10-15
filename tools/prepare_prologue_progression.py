"""Export original prologue challenge/maze/battle links for local progression.

No original account state, rewards, battle result or server execution is inferred.
"""
import hashlib
import json
from pathlib import Path
from extract_game_data import export_table
from trace_first_encounter import literal_table
from extract_texture_samples import APK_SHA256

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/mainline-progression'


def main():
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=APK_SHA256:
            raise ValueError('Original APK changed')
    activity=export_table(4931,[2])
    # challenge_table imports enum metadata; retain only literal constructor data.
    challenges=literal_table(5921,{3997,3998})
    mazes=export_table(1303,[3997,3998])
    battles=[literal_table(4664,{5000}),literal_table(5766,{1703})]
    af=activity['rows'][0]['fields']
    if af['ChallengeList']!=[3997,3998] or af['Close'] is not False or af['Energy']!=0:
        raise ValueError('Reviewed prologue activity changed')
    maze_map={r['id']:r for r in mazes['rows']}
    battle_map={r['id']:r for table in battles for r in table['rows']}
    nodes=[]
    for row in challenges['rows']:
        fields=row['fields']
        if fields['MaxTimes']!=1 or fields['HasLoot'] is not False or fields['MazeIDList']!=[row['id']]:
            raise ValueError('Reviewed prologue challenge policy changed')
        maze=maze_map[row['id']]['fields'];battle=battle_map[maze['LoadingBattleID']]['fields']
        nodes.append(dict(id=row['id'],name=fields['ChallengeName'],subtitle=fields['ChallengeSpecialName'],
            mazeId=row['id'],battleId=maze['LoadingBattleID'],predecessors=fields.get('Unlock',[]),
            maxCompletions=fields['MaxTimes'],hasLoot=fields['HasLoot'],
            loadingSceneId=maze['LoadingBattleScene'][str(maze['LoadingBattleID'])],
            battleSceneId=battle['BattleScene'],monsterIds=[m['MonsterID'] for m in battle['MonsterInfo']],
            story=dict(name=fields['MainlineSLName'],params=fields['MainlineSLParams'])))
    nodes.sort(key=lambda n:n['id'])
    if [(n['id'],n['battleId'],n['predecessors']) for n in nodes]!=[(3997,5000,[]),(3998,1703,[3997])]:
        raise ValueError('Reviewed prologue topology changed')
    result=dict(schemaVersion=1,apkSha256=APK_SHA256,activityId=2,name=af['ActivityName'],nodes=nodes,
        sourceTables=dict(activity=activity,challenges=challenges,mazes=mazes,battles=battles),
        authority='static-original-configuration; not original account or server state',
        limits=['Fresh local progress is an explicit reconstruction policy.',
            'HasLoot=false does not prove the meaning of battle DropPersistentItems; no rewards are granted by this adapter.',
            'Story links and scene associations do not mean those sequences or BOSS mechanics are playable.'])
    OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'prologue.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf8')
    print(json.dumps(dict(path=str(target),sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                          nodes=[dict(id=n['id'],battleId=n['battleId']) for n in nodes])))


if __name__=='__main__':main()
