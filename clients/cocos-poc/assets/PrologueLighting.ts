import { EffectAsset, JsonAsset, Material, MeshRenderer, Node, resources, Texture2D, Vec4 } from 'cc';

/** Diffuse lightmap reference from source parameters; not original full BRDF. */
export async function applyPrologueLighting(root: Node): Promise<Material[]> {
    const [effect, data] = await Promise.all([
        new Promise<EffectAsset>((resolve, reject) => resources.load('recovered/prologue/lightmap', EffectAsset,
            (e, a) => e ? reject(e) : resolve(a))),
        new Promise<JsonAsset>((resolve, reject) => resources.load('recovered/prologue/lightmaps', JsonAsset,
            (e, a) => e ? reject(e) : resolve(a))),
    ]);
    const source = data.json as { images: string[]; bindings: { name: string; submesh: number;
        parameters: Record<string, string> }[] };
    const textures = await Promise.all(source.images.map(path => new Promise<Texture2D>((resolve, reject) =>
        resources.load(path + '/texture', Texture2D, (e, a) => e ? reject(e) : resolve(a)))));
    const nodes = new Map<string, Node[]>();
    const visit = (n: Node): void => { nodes.set(n.name, [...(nodes.get(n.name) ?? []), n]); n.children.forEach(visit); };
    visit(root);
    const materials: Material[] = [];
    try {
        for (const row of source.bindings) {
            const owners = nodes.get(row.name);
            if (owners?.length !== 1 || row.submesh !== 0) throw new Error('场景光照节点匹配失败：' + row.name);
            const renderers = owners[0].getComponentsInChildren(MeshRenderer);
            if (renderers.length !== 1) throw new Error('场景光照网格匹配失败：' + row.name);
            const renderer = renderers[0], old = renderer.getSharedMaterial(0), p = row.parameters;
            if (!old || p.UE4_lm !== 'true' || p.encode_type !== '4') throw new Error('场景光照格式不支持');
            const texture = old.getProperty('mainTexture');
            if (!(texture instanceof Texture2D)) throw new Error('场景原颜色贴图缺失');
            const vec = (name: string): number[] => p[name].split(',').map(Number);
            const scale = vec('lightmap_scale'), add = vec('lightmap_add'), uv = vec('uv_scale'), offset = vec('uv_ofs');
            const material = new Material(); materials.push(material);
            material.initialize({ effectAsset: effect });
            material.setProperty('mainTexture', texture);
            material.setProperty('lightTexture', textures[Number(p.texture_index)]);
            material.setProperty('lightScale', new Vec4(scale[0], scale[1], scale[2], 0));
            material.setProperty('lightAdd', new Vec4(add[0], add[1], add[2], 0));
            material.setProperty('lightUV', new Vec4(uv[0], uv[1], offset[0], offset[1]));
            renderer.setSharedMaterial(material, 0);
        }
        console.info('[HCZS_PROLOGUE] lightmaps bound=' + materials.length);
        return materials;
    } catch (error) { materials.forEach(m => m.destroy()); throw error; }
}
