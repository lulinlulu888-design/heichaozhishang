"""Inspect AI hall icon candidates without changing image pixels or UE assets.

Images are generated with the built-in image_gen tool; this script is only an
ordinary-tool provenance and alpha/padding audit, not an AI image editor or REA.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(path: Path) -> dict:
    with Image.open(path) as image:
        if image.mode != "RGBA":
            raise ValueError(f"Expected RGBA image: {path}")
        alpha = image.getchannel("A")
        histogram = alpha.histogram()
        solid = alpha.point(lambda value: 255 if value >= 128 else 0)
        bbox = solid.getbbox()
        if not bbox:
            raise ValueError(f"No visible icon: {path}")
        width, height = image.size
        normal = [bbox[0] / width, bbox[1] / height, bbox[2] / width, bbox[3] / height]
        return {
            "path": str(path.resolve()),
            "sha256": sha256(path),
            "mode": image.mode,
            "size": [width, height],
            "alphaExtrema": list(alpha.getextrema()),
            "alphaAnyBBox": list(alpha.getbbox()),
            "alpha128BBox": list(bbox),
            "alpha128BBoxNormalized": normal,
            "fullyTransparentPixels": histogram[0],
            "lowAlphaPixels1To31": sum(histogram[1:32]),
            "partialAlphaPixels": sum(histogram[1:255]),
            "fullyOpaquePixels": histogram[255],
        }


def adaptation(source: dict, candidate: dict) -> dict:
    """Suggest UV crop + draw subrectangle; do not modify the PNG or layout."""
    sx0, sy0, sx1, sy1 = source["alpha128BBoxNormalized"]
    gx0, gy0, gx1, gy1 = candidate["alpha128BBoxNormalized"]
    return {
        "method": "review-only-source-alpha128-alignment",
        "textureUVBox": [gx0, gy0, gx1, gy1],
        "drawSubrectangleInOriginalWidget": [sx0, sy0, sx1, sy1],
        "fullCanvasScaleXY": [(sx1 - sx0) / (gx1 - gx0), (sy1 - sy0) / (gy1 - gy0)],
        "fullCanvasOffsetXY": [
            sx0 - gx0 * (sx1 - sx0) / (gx1 - gx0),
            sy0 - gy0 * (sy1 - sy0) / (gy1 - gy0),
        ],
        "caution": "Alpha128 is a geometry heuristic, not original alpha authority. Cropping can remove soft edges. Never use alphaAnyBBox for alignment: AI outputs contain scattered low alpha pixels.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("analysis/unreal/hall-ui/ai-icons/provenance.json"))
    parser.add_argument("--output", type=Path, default=Path("analysis/unreal/hall-ui/ai-icons/audit.json"))
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    items = []
    for item in manifest["icons"]:
        source = inspect(Path(item["source"]["png"]))
        if source["sha256"] != item["source"]["pngSha256"]:
            raise ValueError(f"Original source hash changed: {item['name']}")
        variants = []
        for variant in item["variants"]:
            candidate = inspect(Path(variant["path"]))
            if candidate["sha256"] != variant["sha256"]:
                raise ValueError(f"AI variant hash changed: {item['name']} {variant['version']}")
            variants.append({"version": variant["version"], **candidate, "adaptation": adaptation(source, candidate)})
        items.append({"name": item["name"], "spriteId": item["source"]["spriteId"], "source": source, "variants": variants})
    report = {
        "schemaVersion": 1,
        "evidenceType": "ordinary-tools-image-metadata-and-manual-review",
        "provenanceSha256": sha256(args.manifest),
        "pngMutation": False,
        "ueAssetMutation": False,
        "icons": items,
        "limitations": ["AI fills missing detail; it does not recover original high resolution artwork.", "No automatic silhouette fidelity score or functional UE integration is claimed.", "No normal, mix, alpha-mask, or numeric texture channels are AI edited."],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "icons": len(items), "variants": sum(len(item["variants"]) for item in items), "pngMutation": False, "ueAssetMutation": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
