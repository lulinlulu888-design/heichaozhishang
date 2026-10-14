"""Recover the source scene203 home environment; no original UI/runtime claim."""
import json
from pathlib import Path
from extract_game_data import export_table
from audit_city_scene_dependencies import main as dependencies
from export_city_scene import run as export

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/hall'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    table=export_table(9650,{203})
    row=table['rows'][0]['fields']
    if row['ScenePath']!='scene/midgard_home_3d/midgard_home_3d.scn' or row['SceneType']!='HallSceneHome':
        raise ValueError('Hall source identity changed')
    (OUT/'scene-table.json').write_text(json.dumps(table,ensure_ascii=False,indent=2),'utf8')
    dependencies(('midgard_home_3d',),OUT)
    export('midgard_home_3d',OUT)

if __name__=='__main__':main()
