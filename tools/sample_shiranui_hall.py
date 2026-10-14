"""Sample exact Shiranui and fan clips using the shared reviewed ACL pipeline."""
from pathlib import Path
from recover_shiranui_hall import main as extract
from sample_lynn_idle import sample_pinned
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    extract()
    sample_pinned(ROOT/'analysis/characters/shiranui/idle',
        {'home_stand_idle_1':'4e634f1691d6e807c9f98aed9e46dfc44a06d1b4a665735bad01bb5173e59883'},'shiranui-idle',0)
    sample_pinned(ROOT/'analysis/characters/shiranui/idle-weapon',
        {'home_stand_idle_1':'965334500ad8406ce049ea76e60b30e1a8c0976d6b3e42c16275062fe7271d33'},'shiranui-weapon-idle',1)
