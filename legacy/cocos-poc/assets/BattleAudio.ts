import { AudioClip, AudioSource, JsonAsset, Node, resources, SkeletalAnimation, tween, Tween } from 'cc';

interface Sound { resource: string; volume: number; }
interface Cue { clip: string; ratio: number; event: string; resource?: string; volume?: number;
    variants?: Sound[]; sequence?: string; group?: string; delay?: number; fade?: number; }
interface Voice { node: Node; audio: AudioSource; group?: string; fading: boolean; }

/** Source media/timing with static gain; full Wwise mixing remains incomplete. */
export class BattleAudio {
    private cues: Cue[] = [];
    private clips = new Map<string, AudioClip>();
    private voices = new Set<Voice>();
    private sequences = new Map<string, number>();
    private delayed = new Set<{ target: object; group?: string }>();
    private master = 1;
    private pending = new Set<() => void>();
    private disposed = false;
    constructor(private parent: Node, private manifestPath = 'recovered/audio/cues') {}
    async load(): Promise<void> {
        const manifest = await new Promise<JsonAsset>((resolve, reject) =>
            resources.load(this.manifestPath, JsonAsset, (e, a) => e ? reject(e) : resolve(a)));
        const cues: Cue[] = manifest.json?.cues;
        this.master = manifest.json?.master_volume ?? 1;
        if (!Array.isArray(cues) || cues.some(c => !Number.isFinite(c.ratio) || c.ratio < 0 || c.ratio > 1
            || !Number.isFinite(c.delay ?? 0) || (c.delay ?? 0) < 0
            || !Number.isFinite(c.fade ?? 0) || (c.fade ?? 0) < 0
            || (c.variants !== undefined && (!c.variants.length || !c.sequence || !c.group))
            || this.sounds(c).some(s => !s.resource || !Number.isFinite(s.volume) || s.volume < 0
                || s.volume * this.master > 1))
            || !Number.isFinite(this.master) || this.master < 0 || this.master > 1) throw new Error('声音配置无效');
        for (const cue of cues) {
          for (const sound of this.sounds(cue)) {
            if (this.clips.has(sound.resource)) continue;
            const clip = await new Promise<AudioClip>((resolve, reject) =>
                resources.load(sound.resource, AudioClip, (e, a) => e ? reject(e) : resolve(a)));
            if (this.disposed) return;
            clip.addRef(); this.clips.set(sound.resource, clip);
          }
        }
        if (!this.disposed) this.cues = cues;
    }
    private sounds(cue: Cue): Sound[] {
        return cue.variants ?? [{ resource: cue.resource!, volume: cue.volume! }];
    }
    private release(voice: Voice): void {
        if (!this.voices.delete(voice)) return;
        Tween.stopAllByTarget(voice.audio);
        voice.audio.stop(); voice.node.destroy();
    }
    private trigger(cue: Cue, name: string): void {
        if (cue.group) {
            // A new group event cancels queued voices as well as fading audible ones.
            for (const item of Array.from(this.delayed)) if (item.group === cue.group) {
                Tween.stopAllByTarget(item.target); this.delayed.delete(item);
            }
            for (const voice of Array.from(this.voices)) if (voice.group === cue.group && !voice.fading) {
                voice.fading = true;
                if (!cue.fade) this.release(voice);
                else tween(voice.audio).to(cue.fade, { volume: 0 }).call(() => this.release(voice)).start();
            }
        }
        const sounds = this.sounds(cue);
        const index = cue.sequence ? (this.sequences.get(cue.sequence) ?? 0) : 0;
        const sound = sounds[index % sounds.length];
        if (cue.sequence) this.sequences.set(cue.sequence, (index + 1) % sounds.length);
        const item = { target: {}, group: cue.group };
        const play = (): void => {
            if (this.disposed || !this.delayed.delete(item)) return;
            const clip = this.clips.get(sound.resource);
            if (!clip) return;
            const node = new Node('OriginalBattleSound'); this.parent.addChild(node);
            const audio = node.addComponent(AudioSource);
            const voice: Voice = { node, audio, group: cue.group, fading: false }; this.voices.add(voice);
            audio.playOnAwake = false; audio.loop = false; audio.clip = clip; audio.volume = sound.volume * this.master;
            node.once(AudioSource.EventType.ENDED, () => this.release(voice));
            node.once(AudioSource.EventType.STARTED, () => console.info('[HCZS_AUDIO] started', name, cue.event, sound.resource));
            audio.play();
            console.info('[HCZS_AUDIO] requested', name, cue.event, cue.ratio, audio.volume, sound.resource);
        };
        this.delayed.add(item);
        console.info('[HCZS_AUDIO] event', name, cue.event, cue.delay ?? 0, index);
        // Once the event fires, its delayed play survives normal animation completion.
        if (cue.delay) tween(item.target).delay(cue.delay).call(play).start(); else play();
    }
    playEvent(name: string): boolean {
        if (this.disposed) return false;
        const cues = this.cues.filter(c => c.event === name);
        for (const cue of cues) this.trigger(cue, 'result');
        return cues.length > 0;
    }
    schedule(animation: SkeletalAnimation, name: string): () => void {
        if (this.disposed) return () => {};
        const callbacks: (() => void)[] = [];
        let cancelled = false;
        const cancel = (): void => {
            cancelled = true;
            callbacks.forEach(f => animation.unschedule(f));
            this.pending.delete(cancel);
        };
        this.pending.add(cancel);
        for (const cue of this.cues.filter(c => c.clip === name)) {
            const callback = (): void => {
                if (this.disposed || cancelled) return;
                this.trigger(cue, name);
            };
            callbacks.push(callback);
            animation.scheduleOnce(callback, animation.getState(name).duration * cue.ratio);
        }
        return cancel;
    }
    stop(): void {
        Array.from(this.pending).forEach(cancel => cancel());
        for (const item of this.delayed) Tween.stopAllByTarget(item.target);
        this.delayed.clear();
        Array.from(this.voices).forEach(voice => this.release(voice));
    }
    destroy(): void {
        this.disposed = true; this.stop();
        this.clips.forEach(clip => clip.decRef()); this.clips.clear(); this.cues = [];
        this.sequences.clear();
    }
}
