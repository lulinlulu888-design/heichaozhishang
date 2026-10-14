"""Recover only victory frames bound by the actual BattleWin dialog CSBs."""
from recover_pile_ui_sprites import ROOT, recover

WANTED = {
    'EventSynopsisDialog/Res/SingleEvent/img_event_win.png': 'victory-glow',
    'EventSynopsisDialog/Res/SingleEvent/img_event_win_up.png': 'victory-lettering',
    'EventSynopsisDialog/Res/SingleEvent/perfect.png': 'victory-title',
    'EventSynopsisDialog/Res/SingleEvent/perfect_black.png': 'victory-shadow',
    'EventSynopsisDialog/Res/SingleEvent/img_event_label_underwin.png': 'victory-subtitle',
    'EventSynopsisDialog/Res/SingleEvent/img_event_pattern_underwin.png': 'victory-pattern',
    'EventSynopsisDialog/Res/SingleEvent/img_event_mask.png': 'victory-mask',
}

if __name__ == '__main__':
    recover(WANTED, ROOT/'analysis/battle-ui/result/sprites',
            ROOT/'analysis/battle-ui/result/layouts.json')
