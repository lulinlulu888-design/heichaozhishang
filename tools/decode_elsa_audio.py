"""Decode source-bound Elsa WEMs to one-pass PCM previews, not a Wwise mix."""
import array
import argparse
import hashlib
import json
import re
import subprocess
import struct
import wave
import zipfile

from extract_npk import APK, ROOT
from extract_texture_samples import APK_SHA256
from inspect_enemy_audio import sha, chunks


def voice_media(source, route_name='voice-routes.json'):
    """Bind streamed inputs back to the unchanged APK, not just an old report."""
    with APK.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity changed')
    routes = json.loads((source/route_name).read_text('utf8'))
    media = []
    with zipfile.ZipFile(APK) as archive:
        bank = archive.read(routes['bank_member'])
        if sha(bank) != routes['bank_sha256'] or bank != (source/'ailisha_voice.bnk').read_bytes():
            raise ValueError('voice bank identity changed')
        for ident, item in sorted(routes['media'].items(), key=lambda pair: int(pair[0])):
            original = source/'voice-media'/f'{ident}.wem'
            payload = original.read_bytes()
            if payload != archive.read(item['member']) or sha(payload) != item['sha256'] or len(payload) != item['bytes']:
                raise ValueError('streamed voice identity changed')
            if payload[:4] != b'RIFF' or payload[8:12] != b'WAVE' or struct.unpack_from('<I', payload, 4)[0]+8 != len(payload):
                raise ValueError('invalid voice RIFF envelope')
            fmt = struct.unpack_from('<HHIIHH', chunks(payload, 12)[b'fmt '][1])
            media.append(dict(id=int(ident), source_name=item['member'], sha256=item['sha256'],
                              sample_rate=fmt[2], channels=fmt[1], original=original))
    return media


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--voice', action='store_true', help='Decode the seven source-bound streamed battle voices')
    parser.add_argument('--result-voice', action='store_true', help='Decode source-bound result voices separately')
    args = parser.parse_args()
    if args.voice and args.result_voice: parser.error('Select one voice set')
    prefix = 'result-voice' if args.result_voice else 'voice'
    args.voice = args.voice or args.result_voice
    tool_dir = ROOT/'.tools/vgmstream-r2117'
    release = ROOT/'.tools/vgmstream-r2117-win64.zip'
    if sha(release.read_bytes()) != '6c4a8a3813864fefed081bbd337dbc0ad93bf88e0b92f5db98d7ab258b22dc6c':
        raise ValueError('decoder release identity changed')
    # The extracted decoder and libraries must match the verified upstream ZIP.
    with zipfile.ZipFile(release) as archive:
        for name in archive.namelist():
            if name.endswith(('.exe','.dll')):
                if (tool_dir/name).read_bytes() != archive.read(name):
                    raise ValueError('decoder executable/library changed')
    source = ROOT/'analysis/battle-visual/elsa-audio'
    out = source/(prefix+'-pcm' if args.voice else 'pcm')
    out.mkdir(exist_ok=True)
    if args.voice:
        media = voice_media(source,prefix+'-routes.json')
    else:
        manifest = json.loads((source/'report.json').read_text('utf8'))
        bank = (source/'ailisha_skill.bnk').read_bytes()
        if sha(bank) != manifest['bank_sha256']:
            raise ValueError('bank identity changed')
        media = manifest['media']
    reports = []
    for item in media:
        original = item.get('original', source/f"{item['id']}.wem")
        payload = original.read_bytes()
        if sha(payload) != item['sha256'] or (not args.voice and payload != bank[item['bank_offset']:item['bank_offset']+item['bytes']]):
            raise ValueError('source media identity changed')
        destination = out/f"{item['id']}.wav"
        result = subprocess.run([str(tool_dir/'vgmstream-cli.exe'),'-i','-o',str(destination),str(original)],
                                capture_output=True,text=True,check=True)
        (out/f"{item['id']}.log").write_text(result.stdout+result.stderr,encoding='utf8')
        samples = re.search(r'stream total samples: (\d+)',result.stdout)
        if not samples:
            raise ValueError('decoder did not report source samples')
        with wave.open(str(destination),'rb') as wav:
            frames, rate, channels, width = wav.getnframes(),wav.getframerate(),wav.getnchannels(),wav.getsampwidth()
            if frames != int(samples[1]) or rate != item['sample_rate'] or channels != item['channels'] or width != 2:
                raise ValueError('decoded PCM format/sample-count mismatch')
            pcm = array.array('h',wav.readframes(frames))
        if not pcm or not any(pcm):
            raise ValueError('empty or silent decode')
        reports.append(dict(id=item['id'],source_name=item['source_name'],source_sha256=item['sha256'],
                            pcm_sha256=sha(destination.read_bytes()),frames=frames,sample_rate=rate,
                            channels=channels,duration_seconds=frames/rate,peak=max(abs(v) for v in pcm),
                            rms=(sum(v*v for v in pcm)/len(pcm))**0.5))
    report = dict(evidence_kind='ordinary-local-static-tool', source_kind='voice' if args.voice else 'skill',
                  source_report_sha256=sha((source/(prefix+'-routes.json' if args.voice else 'report.json')).read_bytes()),
                  decoder_release='r2117',release_url='https://github.com/vgmstream/vgmstream/releases/tag/r2117',
                  decoder_sha256=sha((tool_dir/'vgmstream-cli.exe').read_bytes()),media=reports,
                  limitations=['One pass with loops ignored (-i); not original loop/stop behavior.',
                               'No event gain, pitch, bus mix, effects or spatial processing applied.',
                               'Non-silent PCM and sample counts verified, not human listening or game playback.'])
    (source/(prefix+'-decode-report.json' if args.voice else 'decode-report.json')).write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(dict(decoded=len(reports),duration_seconds=sum(r['duration_seconds'] for r in reports))))


if __name__ == '__main__':
    main()
