"""Seven reviewed hall icons; top-bar optical sizing, shared chat/harvest art."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import import_balanced_hall_icons
import import_ai_hall_icons as pipeline

pipeline.PROVENANCE = pipeline.ROOT / 'analysis/unreal/hall-ui/ai-icons/provenance-family.json'
pipeline.AUDIT = pipeline.ROOT / 'analysis/unreal/hall-ui/ai-icons/audit-family.json'
pipeline.PINNED_PROVENANCE = '5b77e89fdf6858eb290971047ce7fd46213fefd4c112cbd0782736f89e03b4a3'
pipeline.PINNED_AUDIT = '3338c5afcbd23aa74dc40ee56890186f92698d06d7258d13f39bb4d6063f03c5'
pipeline.REPORT = pipeline.ROOT / 'analysis/unreal/hall-ui/ai-icons/ue-family-import-result.json'
pipeline.PLAN_REPORT = pipeline.ROOT / 'analysis/unreal/hall-ui/ai-icons/ue-family-input-plan.json'
pipeline.DEST = '/Game/Recovered/Hall/UI/AI/UnifiedV4'
pipeline.LAYOUT_ASSET = pipeline.DEST + '/HallLayoutHDAll'
pipeline.RECIPE_VERSION = 'hczs-hall-ai-icons-seven-family-v4'
pipeline.SELECTION = {'event':2, 'welfare':3, 'friends':2, 'mail':1, 'community':3, 'chat':1, 'harvest':1}
pipeline.REVIEWED_INSTANCE_PREFIXES = ('Layer/Main/RightTop/SysBtn/', 'Layer/Main/LeftBottom/ChatNode/', 'Layer/Main/RightBottom/HomeSignFor/')
pipeline.EXTERNAL_TEXTURE_REFERENCES = {
    'chat': '/Game/Recovered/UI/IconLibrary/AI/T_AI_chat_v1',
    'harvest': '/Game/Recovered/UI/IconLibrary/AI/T_AI_harvest_v1',
}

if __name__ == '__main__':
    pipeline.main()
