#!/usr/bin/env python3
"""Build an offline video reference gallery from reference.json manifests."""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
import tempfile
from pathlib import Path, PureWindowsPath
from urllib.parse import quote


DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "analysis" / "video-references"


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def finite_number(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else default
    except (TypeError, ValueError):
        return default


def timestamp(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


def local_asset(directory: Path, raw_path: object) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("资源路径为空")
    relative = Path(raw_path.replace("\\", "/"))
    if relative.is_absolute() or PureWindowsPath(raw_path).drive:
        raise ValueError(f"资源路径必须相对 reference.json：{raw_path}")
    asset = (directory / relative).resolve()
    if not asset.is_relative_to(directory.resolve()):
        raise ValueError(f"资源路径超出所在参考目录：{raw_path}")
    if not asset.is_file():
        raise ValueError(f"资源不存在：{raw_path}")
    return asset


def asset_url(path: Path, root: Path) -> str:
    # URL-encode Unicode, spaces, # and %, then HTML-escape at the call site.
    return quote(path.relative_to(root).as_posix(), safe="/")


def warn(message: str) -> None:
    print(f"提示：{message}", file=sys.stderr)


def read_reference(manifest: Path, root: Path) -> dict | None:
    try:
        manifest = manifest.resolve()
        if not manifest.is_relative_to(root):
            raise ValueError("清单位于参考库目录之外")
        data = json.loads(manifest.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or data.get("schemaVersion") != 1:
            raise ValueError("不支持的 reference.json 格式；需要 schemaVersion: 1")
        video = data.get("video")
        if not isinstance(video, dict):
            raise ValueError("缺少 video 元数据")
        video_path = local_asset(manifest.parent, video.get("path"))
        frames = []
        for item in data.get("frames", []):
            try:
                if not isinstance(item, dict):
                    raise ValueError("截图条目不是对象")
                seconds = finite_number(item.get("seconds"), -1)
                if seconds < 0:
                    raise ValueError("截图时间无效")
                frame_path = local_asset(manifest.parent, item.get("path"))
                frames.append({"path": frame_path, "seconds": seconds})
            except (ValueError, OSError) as error:
                warn(f"{manifest.parent.name}：跳过截图，{error}")
        frames.sort(key=lambda frame: (frame["seconds"], str(frame["path"])))
        verification = data.get("verification") or {}
        return {
            "directory": manifest.parent,
            "title": str(data.get("title") or manifest.parent.name),
            "bvid": str(data.get("bvid") or ""),
            "cid": str(data.get("cid") or ""),
            "duration": finite_number(data.get("durationSeconds")),
            "width": int(finite_number(video.get("width"))),
            "height": int(finite_number(video.get("height"))),
            "codec": str(video.get("codec") or ""),
            "fps": str(video.get("fps") or ""),
            "video": video_path,
            "frames": frames,
            "verified": isinstance(verification, dict) and verification.get("fullDecode") is True,
        }
    except (ValueError, TypeError, OSError) as error:
        warn(f"跳过 {manifest}：{error}")
        return None


def build_contact_sheet(reference: dict) -> Path | None:
    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError:
        return None
    frames = reference["frames"]
    if not frames:
        return None
    # Keep the overview compact; the HTML gallery still shows every frame.
    if len(frames) > 24:
        frames = [frames[round(index * (len(frames) - 1) / 23)] for index in range(24)]
    columns = min(4, len(frames))
    rows = math.ceil(len(frames) / columns)
    # Four columns plus the gutters make a 1600 px wide overview.
    tile_width, image_height, label_height, gap = 385, 217, 28, 12
    tile_height = image_height + label_height
    sheet = Image.new("RGB", (columns * (tile_width + gap) + gap, rows * (tile_height + gap) + gap), "#131b2b")
    draw = ImageDraw.Draw(sheet)
    loaded = 0
    for index, frame in enumerate(frames):
        x = gap + (index % columns) * (tile_width + gap)
        y = gap + (index // columns) * (tile_height + gap)
        try:
            with Image.open(frame["path"]) as image:
                thumb = ImageOps.contain(image.convert("RGB"), (tile_width, image_height), Image.Resampling.LANCZOS)
                sheet.paste(thumb, (x + (tile_width - thumb.width) // 2, y + (image_height - thumb.height) // 2))
            loaded += 1
            draw.text((x + 8, y + image_height + 7), timestamp(frame["seconds"]), fill="white")
        except (OSError, ValueError) as error:
            draw.text((x + 8, y + 8), "Frame unavailable", fill="white")
            warn(f"截图总览读取失败：{frame['path']}：{error}")
    if not loaded:
        return None
    output = reference["directory"] / "contact-sheet.jpg"
    try:
        sheet.save(output, format="JPEG", quality=90)
        return output
    except OSError as error:
        warn(f"截图总览保存失败：{output}：{error}")
        return None
    finally:
        sheet.close()


def render_reference(reference: dict, index: int, root: Path) -> str:
    video_id = f"video-{index}"
    title = escape(reference["title"])
    video_url = escape(asset_url(reference["video"], root))
    metadata = [timestamp(reference["duration"])]
    if reference["width"] and reference["height"]:
        metadata.append(f"{reference['width']} × {reference['height']}")
    if reference["codec"]:
        metadata.append(reference["codec"])
    identity = " · ".join(value for value in (reference["bvid"], f"CID {reference['cid']}" if reference["cid"] else "") if value)
    poster = f' poster="{escape(asset_url(reference["frames"][0]["path"], root))}"' if reference["frames"] else ""
    frames_html = []
    for frame in reference["frames"]:
        time_label = timestamp(frame["seconds"])
        frames_html.append(
            f'<button class="frame" type="button" data-video="{video_id}" data-seconds="{frame["seconds"]:g}" '
            f'aria-label="跳转到 {time_label}" title="点击跳转到 {time_label}">'
            f'<img src="{escape(asset_url(frame["path"], root))}" alt="{title}，{time_label}" loading="lazy">'
            f'<span>{time_label}</span></button>'
        )
    contact = build_contact_sheet(reference)
    contact_link = f'<a href="{escape(asset_url(contact, root))}" target="_blank" rel="noopener">截图总览 ↗</a>' if contact else ""
    status = '<span class="verified">已完整解码校验</span>' if reference["verified"] else '<span class="unverified">尚未完整解码校验</span>'
    frame_content = "".join(frames_html) or '<p class="muted">此视频尚无参考截图。</p>'
    return f"""
    <article class="reference" data-search="{escape(reference['title'] + ' ' + identity)}">
      <header class="reference-header">
        <div><h2>{title}</h2><p class="metadata">{escape(' · '.join(metadata))}</p><p class="identity">{escape(identity)}</p></div>
        {status}
      </header>
      <video id="{video_id}" controls preload="none" playsinline{poster} aria-label="{title}">
        <source src="{video_url}" type="video/mp4">
        浏览器无法播放此视频，可通过下方链接在本地播放器中打开。
      </video>
      <div class="actions"><span>参考截图 · {len(reference['frames'])} 张 · 点击跳转播放</span><nav>{contact_link}<a href="{video_url}" target="_blank" rel="noopener">打开 MP4 ↗</a></nav></div>
      <div class="frames">{frame_content}</div>
      <p class="player-status" role="status" aria-live="polite"></p>
    </article>"""


STYLE = """
:root { color-scheme: dark; font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; background: #0d1320; color: #e8edf7; }
* { box-sizing: border-box; }
body { margin: 0; }
main { max-width: 1280px; margin: auto; padding: 44px 28px 64px; }
h1 { margin: 0 0 12px; font-size: clamp(27px, 4vw, 38px); letter-spacing: .03em; }
.eyebrow { color: #76d9ce; font-size: 12px; letter-spacing: .2em; margin: 0 0 12px; }
.intro, .muted { color: #9daec6; line-height: 1.7; }
.summary { display: flex; gap: 12px; flex-wrap: wrap; margin: 24px 0; }
.summary span { padding: 10px 16px; background: #192336; border-radius: 10px; color: #bbc9dc; }
.summary strong { color: #ecf2ff; padding-right: 4px; }
.search { display: block; margin: 24px 0 32px; color: #bdcbe0; }
.search input { display: block; width: 100%; margin-top: 10px; padding: 15px 18px; font: inherit; color: #eef3ff; background: #151f30; border: 1px solid #35455f; border-radius: 12px; }
.search input:focus-visible, button:focus-visible, a:focus-visible { outline: 2px solid #76d9ce; outline-offset: 4px; }
.reference { margin-bottom: 32px; padding: 24px; border: 1px solid #2b374b; border-radius: 18px; background: #151e2d; }
.reference-header { display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; }
h2 { margin: 0; font-size: 21px; overflow-wrap: anywhere; line-height: 1.5; }
.metadata { margin: 8px 0; color: #c2cfe1; }
.identity { margin: 0 0 18px; color: #8192ac; font-size: 12px; overflow-wrap: anywhere; }
.verified, .unverified { flex: 0 0 auto; font-size: 12px; padding: 7px 10px; border-radius: 6px; }
.verified { color: #90dfc4; background: #1b3836; }
.unverified { color: #e7bf78; background: #3a3023; }
video { display: block; width: 100%; max-height: 70vh; aspect-ratio: 16 / 9; background: #05080d; border-radius: 10px; object-fit: contain; }
.actions { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin: 20px 0 14px; font-size: 13px; color: #9daec6; flex-wrap: wrap; }
nav { display: flex; gap: 20px; }
a { color: #8be0d8; text-decoration: none; }
a:hover { text-decoration: underline; }
.frames { display: flex; gap: 12px; overflow-x: auto; padding: 4px 4px 14px; scrollbar-color: #455773 #111a28; }
.frame { flex: 0 0 192px; padding: 0; border: 1px solid #38475e; border-radius: 8px; background: #101827; color: #dce6f6; cursor: pointer; overflow: hidden; font: inherit; }
.frame:hover, .frame.active { border-color: #76d9ce; }
.frame img { display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: contain; background: #080d16; }
.frame span { display: block; padding: 8px 10px; font-size: 13px; font-variant-numeric: tabular-nums; }
.player-status { min-height: 1em; margin: 6px 0 0; color: #e7bf78; font-size: 13px; }
.empty { padding: 36px; border: 1px dashed #40516e; border-radius: 14px; color: #a7b8d0; line-height: 1.8; }
[hidden] { display: none !important; }
@media (max-width: 640px) { main { padding: 28px 14px; } .reference { padding: 16px; } .reference-header { flex-direction: column; gap: 0; } .verified, .unverified { margin-bottom: 16px; } .frame { flex-basis: 160px; } }
"""


SCRIPT = """
const search = document.querySelector('#search');
const references = [...document.querySelectorAll('.reference')];
search.addEventListener('input', () => {
  const query = search.value.trim().toLocaleLowerCase();
  let visible = 0;
  for (const reference of references) {
    reference.hidden = !reference.dataset.search.toLocaleLowerCase().includes(query);
    if (!reference.hidden) visible++;
  }
  document.querySelector('#no-results').hidden = visible > 0 || references.length === 0;
});
document.querySelectorAll('video').forEach(video => {
  video.addEventListener('play', () => {
    document.querySelectorAll('video').forEach(other => { if (other !== video) other.pause(); });
  });
  video.addEventListener('error', () => {
    video.closest('.reference').querySelector('.player-status').textContent = '浏览器暂时无法解码此视频，请使用“打开 MP4”或本地播放器查看。';
  });
});
document.querySelectorAll('.frame').forEach(button => {
  button.addEventListener('click', () => {
    const video = document.getElementById(button.dataset.video);
    const reference = button.closest('.reference');
    reference.querySelectorAll('.frame').forEach(frame => frame.classList.toggle('active', frame === button));
    reference.querySelector('.player-status').textContent = '';
    video.dataset.seekTo = button.dataset.seconds;
    const seekAndPlay = () => {
      const requested = Number(video.dataset.seekTo);
      video.currentTime = Number.isFinite(video.duration) ? Math.min(requested, Math.max(0, video.duration - 0.01)) : requested;
      video.play().catch(() => {
        reference.querySelector('.player-status').textContent = '已定位截图时间；点击播放器的播放按钮即可继续。';
      });
    };
    if (video.readyState >= 1) seekAndPlay();
    else {
      if (!video.dataset.awaitingMetadata) {
        video.dataset.awaitingMetadata = '1';
        video.addEventListener('loadedmetadata', () => {
          delete video.dataset.awaitingMetadata;
          seekAndPlay();
        }, { once: true });
        video.load();
      }
    }
  });
});
"""


def build_gallery(root: Path) -> Path:
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    references = []
    for manifest in sorted(root.rglob("reference.json"), key=lambda path: str(path).casefold()):
        reference = read_reference(manifest, root)
        if reference is not None:
            references.append(reference)
    cards = "\n".join(render_reference(reference, index, root) for index, reference in enumerate(references))
    if not cards:
        cards = '<p class="empty">暂无可用视频。将转换后的 MP4、截图和 reference.json 放在此目录或子目录中，再运行生成脚本。</p>'
    frame_count = sum(len(reference["frames"]) for reference in references)
    duration = timestamp(sum(reference["duration"] for reference in references))
    document = f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>黑潮之上 · 视频参考库</title><style>{STYLE}</style></head>
<body><main>
  <p class="eyebrow">HCZS · VIDEO REFERENCES</p>
  <h1>黑潮之上 · 视频参考库</h1>
  <p class="intro">对照原版画面与操作表现。视频和截图均从本地读取，点击时间点截图即可定位播放。</p>
  <div class="summary"><span><strong>{len(references)}</strong> 段视频</span><span><strong>{frame_count}</strong> 张截图</span><span>总时长 <strong>{duration}</strong></span></div>
  <label class="search">查找视频<input id="search" type="search" placeholder="搜索标题、BV 号或 CID" autocomplete="off"></label>
  <p id="no-results" class="empty" hidden>没有匹配的视频，请调整搜索内容。</p>
  {cards}
</main><script>{SCRIPT}</script></body></html>
"""
    output = root / "index.html"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, suffix=".tmp", delete=False) as temporary:
        temporary.write(document)
        temporary_path = Path(temporary.name)
    try:
        temporary_path.replace(output)
    finally:
        temporary_path.unlink(missing_ok=True)
    print(f"已生成：{output}\n视频：{len(references)}；截图：{frame_count}；总时长：{duration}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="从 reference.json 生成可离线打开的视频参考库")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=f"参考库根目录（默认：{DEFAULT_ROOT}）")
    args = parser.parse_args()
    build_gallery(args.root)


if __name__ == "__main__":
    main()
