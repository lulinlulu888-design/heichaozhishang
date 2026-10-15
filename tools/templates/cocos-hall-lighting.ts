import { Color, EffectAsset, gfx, Material, MeshRenderer, Node, resources, Texture2D, Vec3, Vec4 } from 'cc';

export interface HallLightmapData {
    schema: number;
    textures: { resource: string }[];
    bindings: { uuid: string; name: string; nodeName: string; primitive: number; uv_count: number; cullBack: boolean;
        parameters: Record<string, string> }[];
    unresolved?: unknown[];
}

export interface HallLightingController {
    readonly enabled: boolean;
    readonly report: { installed_instances: number; deferred_instances: number; scope: string };
    setEnabled(enabled: boolean): void;
    dispose(): void;
}

/** Original baked irradiance applied to diffuse colour only; not original BRDF/HDR. */
export async function installHallLighting(world: Node, data: HallLightmapData): Promise<HallLightingController> {
    if (data.schema !== 1 || !Array.isArray(data.bindings) || !Array.isArray(data.textures)
        || data.bindings.length !== 66 || data.textures.length !== 10) {
        throw new Error('大厅光照清单版本或数量不匹配');
    }
    const nodes = new Map<string, Node[]>();
    const visit = (node: Node): void => {
        nodes.set(node.name, [...(nodes.get(node.name) ?? []), node]);
        node.children.forEach(visit);
    };
    visit(world);
    const entries: { renderer: MeshRenderer; original: Material; material: Material }[] = [];
    const textures: Texture2D[] = [];
    let effect: EffectAsset | null = null;
    let enabled = false, disposed = false;
    try {
        effect = await new Promise<EffectAsset>((resolve, reject) =>
            resources.load('recovered/hall/lightmap', EffectAsset, (error, asset) => error ? reject(error) : resolve(asset)));
        effect.addRef();
        // Sequential acquisition makes partial failures release exactly the references already acquired.
        for (const row of data.textures) {
            if (!/^recovered\/hall\/lightmap_\d+$/.test(row.resource)) throw new Error('大厅光照贴图路径非法');
            const texture = await new Promise<Texture2D>((resolve, reject) =>
                resources.load(row.resource + '/texture', Texture2D, (error, asset) => error ? reject(error) : resolve(asset)));
            texture.addRef(); textures.push(texture);
            texture.setWrapMode(Texture2D.WrapMode.CLAMP_TO_EDGE, Texture2D.WrapMode.CLAMP_TO_EDGE);
            texture.setFilters(Texture2D.Filter.LINEAR, Texture2D.Filter.LINEAR);
            texture.setMipFilter(Texture2D.Filter.NONE);
        }
        if (!world.isValid) throw new Error('大厅节点已释放');
        const used = new Set<string>();
        for (const row of data.bindings) {
            if (used.has(row.nodeName) || !/^HallSource_\d+$/.test(row.nodeName) || row.primitive !== 0) {
                throw new Error('大厅光照重复或不支持的节点：' + row.name);
            }
            used.add(row.nodeName);
            const owners = nodes.get(row.nodeName);
            if (owners?.length !== 1) throw new Error('大厅光照节点匹配失败：' + row.nodeName);
            const renderers = owners[0].getComponentsInChildren(MeshRenderer);
            if (renderers.length !== 1) throw new Error('大厅光照网格数量不匹配：' + row.name);
            const renderer = renderers[0], mesh = renderer.mesh;
            const original = renderer.getSharedMaterial(0);
            if (!mesh || mesh.struct.primitives.length !== 1 || renderer.sharedMaterials.length !== 1 || !original) {
                throw new Error('大厅光照仅支持单网格单材质：' + row.name);
            }
            const uv = mesh.readAttribute(0, gfx.AttributeName.ATTR_TEX_COORD1);
            if (!uv || uv.length !== row.uv_count * 2) throw new Error('大厅光照原 UV1 缺失或数量不符：' + row.name);
            for (let i = 0; i < uv.length; i++) if (!Number.isFinite(uv[i])) throw new Error('大厅光照 UV1 非有限');
            const p = row.parameters;
            if (p.UE4_lm !== 'true' || p.encode_type !== '4') throw new Error('大厅光照编码未支持');
            const index = Number(p.texture_index);
            if (!Number.isInteger(index) || index < 0 || index >= textures.length) throw new Error('大厅光照索引越界');
            const vec = (key: string, count: number): number[] => {
                const values = (p[key] ?? '').split(',').map(Number);
                if (values.length < count || !values.every(Number.isFinite)) throw new Error('大厅光照参数非法：' + key);
                return values;
            };
            const scale = vec('lightmap_scale', 3), add = vec('lightmap_add', 3);
            const offset = vec('uv_ofs', 2), uvScale = vec('uv_scale', 2);
            const base = original.getProperty('mainTexture');
            if (!(base instanceof Texture2D)) throw new Error('大厅原颜色贴图缺失：' + row.name);
            const pass = original.passes[0];
            if (!pass) throw new Error('大厅原材质通道缺失');
            const material = new Material();
            entries.push({ renderer, original, material });
            original.addRef();
            // Preserve existing face culling, transparency and depth behavior; no new dynamic light.
            material.initialize({ effectAsset: effect, defines: { HALL_LIGHTMAP: true }, states: {
                rasterizerState: { ...pass.rasterizerState, cullMode: row.cullBack ? gfx.CullMode.BACK : gfx.CullMode.NONE },
                depthStencilState: pass.depthStencilState,
                blendState: pass.blendState,
            }});
            material.setProperty('mainTexture', base);
            material.setProperty('lightTexture', textures[index]);
            const tint = original.getProperty('mainColor');
            if (tint instanceof Color || tint instanceof Vec4) material.setProperty('mainColor', tint);
            const tiling = original.getProperty('tilingOffset');
            if (tiling instanceof Vec4) material.setProperty('tilingOffset', tiling);
            const colorScale = original.getProperty('colorScale');
            if (colorScale instanceof Vec3) material.setProperty('colorScale', colorScale);
            const renderOptions = original.getProperty('renderOptions');
            if (renderOptions instanceof Vec4) material.setProperty('renderOptions', renderOptions);
            material.setProperty('lightScale', new Vec4(scale[0], scale[1], scale[2], 0));
            material.setProperty('lightAdd', new Vec4(add[0], add[1], add[2], 0));
            material.setProperty('lightUV', new Vec4(uvScale[0], uvScale[1], offset[0], offset[1]));
        }
    } catch (error) {
        entries.forEach(entry => { entry.material.destroy(); entry.original.decRef(); });
        textures.forEach(texture => texture.decRef());
        effect?.decRef();
        throw error;
    }
    const report = { installed_instances: entries.length, deferred_instances: data.unresolved?.length ?? 0,
        scope: 'Original source baked diffuse reference; original BRDF, character lighting and HDR unverified' };
    return {
        get enabled(): boolean { return enabled; },
        report,
        setEnabled(value: boolean): void {
            if (disposed) return;
            enabled = value;
            for (const entry of entries) if (entry.renderer.isValid) {
                entry.renderer.setSharedMaterial(value ? entry.material : entry.original, 0);
            }
        },
        dispose(): void {
            if (disposed) return;
            disposed = true; enabled = false;
            for (const entry of entries) {
                if (entry.renderer.isValid) entry.renderer.setSharedMaterial(entry.original, 0);
                entry.material.destroy(); entry.original.decRef();
            }
            textures.forEach(texture => texture.decRef());
            effect?.decRef();
        },
    };
}

/** Fix GLB OPAQUE alpha for the render texture; leave source BLEND slots untouched. */
export async function installHallBaseMaterials(world: Node, rows: {nodeName: string; slot: number; cullBack: boolean}[]):
    Promise<{dispose(): void; report: {installed_materials: number}}> {
    const effect = await new Promise<EffectAsset>((resolve, reject) =>
        resources.load('recovered/hall/lightmap', EffectAsset, (error, asset) => error ? reject(error) : resolve(asset)));
    effect.addRef();
    const entries: {renderer: MeshRenderer; slot: number; original: Material; material: Material}[] = [];
    let disposed = false;
    try {
        if (!world.isValid) throw new Error('大厅节点已释放');
        const nodes = new Map<string, Node[]>();
        const visit = (n: Node): void => { nodes.set(n.name, [...(nodes.get(n.name) ?? []), n]); n.children.forEach(visit); };
        visit(world);
        const used = new Set<string>();
        for (const row of rows) {
            const key = row.nodeName + ':' + row.slot;
            if (used.has(key) || !/^HallSource_\d+$/.test(row.nodeName) || !Number.isInteger(row.slot) || row.slot < 0) {
                throw new Error('大厅不透明材质绑定非法');
            }
            used.add(key);
            const owners = nodes.get(row.nodeName);
            if (owners?.length !== 1) throw new Error('大厅不透明节点不唯一');
            const renderers = owners[0].getComponentsInChildren(MeshRenderer);
            if (renderers.length !== 1) throw new Error('大厅不透明网格不唯一');
            const renderer = renderers[0], original = renderer.getSharedMaterial(row.slot);
            const texture = original?.getProperty('mainTexture');
            if (!original || !(texture instanceof Texture2D) || row.slot >= renderer.sharedMaterials.length) {
                throw new Error('大厅不透明颜色贴图缺失');
            }
            const material = new Material();
            original.addRef(); entries.push({renderer, slot: row.slot, original, material});
            material.initialize({effectAsset: effect, defines: {HALL_LIGHTMAP: false}, states: {
                rasterizerState: {cullMode: row.cullBack ? gfx.CullMode.BACK : gfx.CullMode.NONE},
                depthStencilState: {depthTest: true, depthWrite: true},
                blendState: {targets: [{blend: false}]},
            }});
            material.setProperty('mainTexture', texture);
            material.setProperty('renderOptions', new Vec4(1, 0, 0, 0));
            const tint = original.getProperty('mainColor');
            if (tint instanceof Color || tint instanceof Vec4) material.setProperty('mainColor', tint);
            const tiling = original.getProperty('tilingOffset');
            if (tiling instanceof Vec4) material.setProperty('tilingOffset', tiling);
            const colorScale = original.getProperty('colorScale');
            if (colorScale instanceof Vec3) material.setProperty('colorScale', colorScale);
        }
        // All rows validated before changing any renderer.
        entries.forEach(entry => entry.renderer.setSharedMaterial(entry.material, entry.slot));
    } catch (error) {
        for (const entry of entries) {
            if (entry.renderer.isValid && entry.renderer.getSharedMaterial(entry.slot) === entry.material) {
                entry.renderer.setSharedMaterial(entry.original, entry.slot);
            }
            entry.material.destroy(); entry.original.decRef();
        }
        effect.decRef(); throw error;
    }
    return { report: {installed_materials: entries.length}, dispose(): void {
        if (disposed) return;
        disposed = true;
        for (const entry of entries) {
            if (entry.renderer.isValid) entry.renderer.setSharedMaterial(entry.original, entry.slot);
            entry.material.destroy(); entry.original.decRef();
        }
        effect.decRef();
    }};
}

/** Match glTF non-transparent output alpha before the hall RT is composited by Sprite. */
export async function installHallCharacterBaseMaterials(root: Node,
    rows: {slot: number; alphaMode: 'OPAQUE' | 'MASK'; alphaCutoff?: number}[]):
    Promise<{dispose(): void; report: {installed_materials: number}}> {
    const effect = await new Promise<EffectAsset>((resolve, reject) =>
        resources.load('recovered/hall/lightmap', EffectAsset, (error, asset) => error ? reject(error) : resolve(asset)));
    effect.addRef();
    const entries: {renderer: MeshRenderer; slot: number; original: Material; material: Material}[] = [];
    let disposed = false;
    try {
        if (!root.isValid) throw new Error('角色节点已释放');
        const renderers = root.getComponentsInChildren(MeshRenderer);
        if (renderers.length !== 1) throw new Error('角色颜色参考需要唯一 MeshRenderer');
        const renderer = renderers[0];
        const used = new Set<number>();
        for (const row of rows) {
            if (!Number.isInteger(row.slot) || row.slot < 0 || used.has(row.slot)
                || (row.alphaMode !== 'MASK' && row.alphaMode !== 'OPAQUE')) {
                throw new Error('角色颜色参考槽或 alphaMode 非法');
            }
            used.add(row.slot);
            const cutoff = row.alphaCutoff ?? .5;
            if (row.alphaMode === 'MASK' && (!Number.isFinite(cutoff) || cutoff < 0 || cutoff > 1)) {
                throw new Error('角色 MASK 阈值非法');
            }
            const original = renderer.getSharedMaterial(row.slot);
            const texture = original?.getProperty('mainTexture');
            if (!original || !(texture instanceof Texture2D) || row.slot >= renderer.sharedMaterials.length) {
                throw new Error('角色原颜色材质缺失：' + row.slot);
            }
            const pass = original.passes[0];
            if (!pass) throw new Error('角色原材质通道缺失');
            const material = new Material();
            original.addRef(); entries.push({renderer, slot: row.slot, original, material});
            // SkinnedMeshRenderer adds its skinning macros through the normal Cocos model path.
            // The effect's CCVertInput includes both baked and realtime skinning variants.
            material.initialize({effectAsset: effect, defines: {HALL_LIGHTMAP: false}, states: {
                rasterizerState: pass.rasterizerState,
                depthStencilState: {depthTest: true, depthWrite: true},
                blendState: {targets: [{blend: false}]},
            }});
            material.setProperty('mainTexture', texture);
            material.setProperty('renderOptions', new Vec4(1, row.alphaMode === 'MASK' ? 1 : 0, cutoff, 0));
            const tint = original.getProperty('mainColor');
            if (tint instanceof Color || tint instanceof Vec4) material.setProperty('mainColor', tint);
            const tiling = original.getProperty('tilingOffset');
            if (tiling instanceof Vec4) material.setProperty('tilingOffset', tiling);
            const colorScale = original.getProperty('colorScale');
            if (colorScale instanceof Vec3) material.setProperty('colorScale', colorScale);
        }
        entries.forEach(entry => entry.renderer.setSharedMaterial(entry.material, entry.slot));
    } catch (error) {
        for (const entry of entries) {
            if (entry.renderer.isValid && entry.renderer.getSharedMaterial(entry.slot) === entry.material) {
                entry.renderer.setSharedMaterial(entry.original, entry.slot);
            }
            entry.material.destroy(); entry.original.decRef();
        }
        effect.decRef(); throw error;
    }
    return {report: {installed_materials: entries.length}, dispose(): void {
        if (disposed) return;
        disposed = true;
        for (const entry of entries) {
            if (entry.renderer.isValid) entry.renderer.setSharedMaterial(entry.original, entry.slot);
            entry.material.destroy(); entry.original.decRef();
        }
        effect.decRef();
    }};
}
