"""Reviewed white-outline icon family; keeps original and previous HD assets.

Reuse the shared, hash-verified PNG/geometry/import pipeline. No image pixels
are edited here. --validate-only works without Unreal; editor uses SaveAsset.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import import_ai_hall_icons as pipeline

pipeline.PROVENANCE = pipeline.ROOT / 'analysis/unreal/hall-ui/ai-icons/provenance-unified.json'
pipeline.AUDIT = pipeline.ROOT / 'analysis/unreal/hall-ui/ai-icons/audit-unified.json'
pipeline.REPORT = pipeline.ROOT / 'analysis/unreal/hall-ui/ai-icons/ue-unified-import-result.json'
pipeline.PLAN_REPORT = pipeline.ROOT / 'analysis/unreal/hall-ui/ai-icons/ue-unified-input-plan.json'
pipeline.DEST = '/Game/Recovered/Hall/UI/AI/UnifiedV2'
pipeline.LAYOUT_ASSET = pipeline.DEST + '/HallLayoutHDUnified'
pipeline.RECIPE_VERSION = 'hczs-hall-ai-icons-white-stroke-v2'
pipeline.PINNED_PROVENANCE = '31da58723df19245f2341b073a38d6fec45851134bf5e3f32220a33ebd3a4946'
pipeline.PINNED_AUDIT = '5a76df54bee3bc122aef1f3c28e51321d53d0e6fe46c6592c96c389efba43b6a'
pipeline.SELECTION = {'event': 2, 'welfare': 3, 'friends': 2, 'mail': 1, 'community': 3}
pipeline.LABEL_STYLE_OVERRIDES = {
    label: {'outlineEnabled': False, 'outlineSize': 0, 'shadowEnabled': False}
    for label in ('事件', '福利', '好友', '邮箱', '社区')
}

if __name__ == '__main__':
    pipeline.main()
