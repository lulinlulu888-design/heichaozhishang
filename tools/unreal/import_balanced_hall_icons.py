"""Match top-bar visible sizes/centres, without changing source or PNG pixels."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import import_unified_hall_icons
import import_ai_hall_icons as pipeline

pipeline.REPORT = pipeline.ROOT / 'analysis/unreal/hall-ui/ai-icons/ue-balanced-import-result.json'
pipeline.PLAN_REPORT = pipeline.ROOT / 'analysis/unreal/hall-ui/ai-icons/ue-balanced-input-plan.json'
pipeline.DEST = '/Game/Recovered/Hall/UI/AI/UnifiedV3'
pipeline.LAYOUT_ASSET = pipeline.DEST + '/HallLayoutHDBalanced'
pipeline.RECIPE_VERSION = 'hczs-hall-ai-icons-optical-size-v3'
pipeline.OPTICAL_BOUNDS_POLICY = {
    'names': ['event', 'welfare', 'friends', 'mail', 'community'],
    'targetBBoxArea': 34 * 34,
    'maxEdge': 40,
    'centre': 'original button centre',
    'aspectRatio': 'preserve source visible body aspect',
    'scope': 'top-bar icon family only, not all game icons',
}

if __name__ == '__main__':
    pipeline.main()
