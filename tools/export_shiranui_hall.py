"""Export source Shiranui using the shared verified mesh/texture/animation pipeline."""
from pathlib import Path
from export_lynn_model import export_character

if __name__=='__main__':
    export_character(Path(__file__).resolve().parents[1]/'analysis/characters/shiranui/export',
        'character/player/buzhihuo/buzhihuo_yangcheng.gim',
        'character\\player\\buzhihuo\\buzhihuo.gisacl','home_stand_idle_1','Shiranui')
    export_character(Path(__file__).resolve().parents[1]/'analysis/characters/shiranui/export-weapon',
        'character/player/buzhihuo/buzhihuo_weapon.gim',
        'character\\player\\buzhihuo\\buzhihuo_weapon.gisacl','home_stand_idle_1','ShiranuiWeapon',
        Path(__file__).resolve().parents[1]/'analysis/characters/shiranui/idle-weapon')
