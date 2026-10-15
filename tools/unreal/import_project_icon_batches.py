"""Full Editor orchestration: source battle UI, HD battle, common pool, hall."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

def main():
    steps = []
    try:
        import import_battle_ui
        import_battle_ui.main()
        steps.append('source-battle-presentation')
        import import_battle_ui_hd
        import_battle_ui_hd.main()
        steps.append('six-hd-battle-icons')
        import import_common_icon_library
        import_common_icon_library.main()
        steps.append('ten-common-library-icons')
        import import_hall_icon_family
        import import_ai_hall_icons
        import_ai_hall_icons.main()
        steps.append('seven-hall-icons-and-optical-size')
    except Exception as error:
        (ROOT / 'analysis/assets/project-icons-ue-result.json').write_text(json.dumps({'passed':False,'completed':steps,'error':str(error)},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        raise
    (ROOT / 'analysis/assets/project-icons-ue-result.json').write_text(json.dumps({'passed':True,'completed':steps,'scope':'21 selected unique source icons; unrelated namespace art not claimed'},ensure_ascii=False,indent=2)+'\n',encoding='utf8')

if __name__ == '__main__':
    main()
