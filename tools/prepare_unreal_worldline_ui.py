"""Convert the original worldline page and chapter templates into UE draw data.

The page renderer contains original static art only.  Empty original ScrollView
slots stay empty until real chapter/progress bindings are recovered.  Template
design strings are preserved for audit but are never submitted as player state.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from audit_hall_ui_dependencies import ui_path
from audit_worldline_ui_dependencies import ENTRY, OUT as DEP, digest
from extract_texture_samples import APK_SHA256
from prepare_unreal_hall_ui import geometry, multiply, rgba, transform, verified

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/unreal/worldline-ui'
PIXELS=ROOT/'analysis/worldline/ui-sprites/report.json'
REA=ROOT/'analysis/rea/initial-artifact-evidence.json'
SCHEMA=ROOT/'tools/reference/cocos2dx/CSParseBinary.fbs'
TITLE=ROOT/'analysis/worldline-ui/title-localization.json'
TITLE_SHA='4fb8ed63acedfedc280b39e57d30b2c317a6d1bd76a54274f53f7dc991f4cc2c'


def exclusion(layout,node,path):
    """Local omission policy, not recovered original runtime visibility."""
    leaf=Path(layout).name
    if leaf.startswith('Topbar_Right'):
        return 'account-currencies-and-runtime-toolbar-placement-unrestored'
    if 'Panel_Qipao' in path:
        return 'branch-notification-state-unrestored'
    if leaf=='VX_Effect_loop_glow_ext.csb' or node.get('classname')=='Particle':
        return 'original-particle-and-timeline-rendering-not-converted'
    if node.get('name') in ('Btn_branch_Glow_S','Btn_branch_Glow_S_1'):
        return 'original-timeline-and-additive-glow-unrestored'
    if node.get('classname')=='Button' and node.get('text') in ('Button','button'):
        # Only the text is omitted below; original normal button art stays.
        return None
    return None


def build():
    report_path=DEP/'report.json'
    report=json.loads(report_path.read_text('utf8'))
    pixels=json.loads(PIXELS.read_text('utf8'))
    verified(TITLE,TITLE_SHA)
    title=json.loads(TITLE.read_text('utf8'))
    if title['consumer']['key']!='MAIN_LINE_TITLE' or title['resolved_original_title']!='世界线':
        raise ValueError('Original worldline title binding changed')
    if report['entry']!=ENTRY or report['apk_sha256']!=APK_SHA256 or pixels['apk_sha256']!=APK_SHA256:
        raise ValueError('Worldline input identity mismatch')
    if pixels['dependency_report_sha256']!=digest(report_path):
        raise ValueError('Worldline dependency graph changed')
    sources=[]
    layouts={}
    for row in report['layouts']:
        path=verified(row['source']['sample_path'],row['source']['sha256'])
        layouts[row['path']]=row['tree']
        sources.append(dict(path=row['path'],csb=str(path),source=row['source'],nodeCount=row['node_count']))
    sprites=[]
    sprite_map={}
    for row in pixels['frames']:
        png=verified(row['png'],row['sha256'])
        item=dict(id=png.stem,plist=row['plist'],sourceFrame=row['source_frame'],png=str(png),
                  pngSha256=row['sha256'],size=row['size'],atlasFrame=row['frame'],untrimmed=True)
        sprites.append(item)
        sprite_map[(row['plist'],row['source_frame'])]=item
    for row in pixels['files']:
        png=verified(row['png'],row['sha256'])
        item=dict(id='standalone_'+digest(png)[:24],logicalPath=row['logical_path'],png=str(png),
                  pngSha256=row['sha256'],size=row['size'],source=row['source'],resolution=row['resolution'])
        sprites.append(item)
        sprite_map[(None,row['logical_path'])]=item
    fonts=[]
    font_map={}
    for row in pixels['fonts']:
        path=verified(row['path'],row['sha256'])
        item=dict(id=path.stem,logicalPath=row['logical_path'],ttf=str(path),sha256=row['sha256'],source=row['source'])
        fonts.append(item)
        font_map[row['logical_path']]=item

    def convert(entry):
        nodes,items,controls,gaps=[],[],[],[]
        def visit(node,layout,parent,world,visible,opacity,path,clip_ids,excluded=None,stack=()):
            if len(nodes)>2000 or len(stack)>32:
                raise ValueError('Worldline expansion bounds exceeded')
            name=node.get('name') or '<opaque>'
            full_path=path+[name]
            node_id='n'+str(len(nodes)).zfill(4)
            reason=excluded or exclusion(layout,node,full_path)
            meta={k:v for k,v in node.items() if k!='children'}
            meta.update(id=node_id,parentId=parent,layout=layout,instancePath='/'.join(full_path),
                        previewExcludedReason=reason)
            nodes.append(meta)
            if node.get('options_status'):
                gaps.append(dict(kind='opaque-options',nodeId=node_id))
                return
            world=multiply(world,transform(node))
            visible=visible and node['visible']
            opacity*=node['alpha']/255
            size=list(node.get('size') or [0,0])
            clips=list(clip_ids)
            if node.get('clip_enabled'):
                meta['clipGeometry']=geometry(world,size)
                clips.append(node_id)
            meta.update(worldMatrixBottomLeft=world,effectiveVisible=visible,effectiveOpacity=opacity)
            children=sorted(enumerate(node['children']),key=lambda pair:(pair[1].get('z_order',0),pair[0]))
            for _,child in children:
                if child.get('z_order',0)<0:
                    visit(child,layout,node_id,world,visible,opacity,full_path,clips,reason,stack)
            def draw(kind):
                return dict(id=node_id+'-'+kind,nodeId=node_id,kind=kind,layout=layout,
                    instancePath='/'.join(full_path),size=size,visible=visible,opacity=opacity,
                    geometry=geometry(world,size),color=rgba(node.get('color_argb')),
                    clipNodeIds=clips,previewExcludedReason=reason,sourceOffset=node['offset'],
                    sourceActionTag=node.get('action_tag',0),paintIndex=len(items))
            ref=node.get('resource') or node.get('background_resource')
            if node['classname']=='Particle':
                gaps.append(dict(kind='particle-emitter',nodeId=node_id,resource=ref))
            elif ref and ref.get('path'):
                sprite=sprite_map.get((ui_path(ref['plist']),ref['path'])) if ref.get('plist') else sprite_map.get((None,ui_path(ref['path'])))
                if not sprite:
                    raise ValueError('Missing verified original UI image: '+str(ref))
                size=[size[i] or sprite['size'][i] for i in range(2)]
                item=draw('sprite')
                item.update(spriteId=sprite['id'],flipX=node.get('flip_x',False),flipY=node.get('flip_y',False),
                    scale9Enabled=node.get('scale9_enabled',False),capInsets=node.get('cap_insets'),
                    blendFunc=node.get('blend_func'))
                items.append(item)
                if node['classname']=='Button' and layout==ENTRY and name=='Btn_branch':
                    controls.append(dict(action='branch-unavailable',size=size,geometry=item['geometry'],enabled=False,
                        authority='original-source-hitbox; story-state-not-restored'))
                if node['classname']=='Button' and Path(layout).name=='Topbar_left_ext.csb' and name=='btn_back':
                    controls.append(dict(action='back',size=size,geometry=item['geometry'],enabled=True,
                        authority='original-source-hitbox; local-close-adaptation'))
                if node['classname']=='Button' and Path(layout).name=='Topbar_left_ext.csb' and name=='btn_info':
                    controls.append(dict(action='info-unavailable',size=size,geometry=item['geometry'],enabled=False))
            if node.get('text'):
                item=draw('text')
                ref=node.get('font_resource') or {}
                font=font_map.get(ui_path(ref['path'])) if ref.get('path') else None
                if node['classname'] not in ('Text','Button') or not font:
                    gaps.append(dict(kind='text-font',nodeId=node_id,text=node['text']))
                else:
                    item.update(text=node['text'],fontId=font['id'],fontSize=node.get('font_size',0),
                        color=rgba(node.get('text_color_argb') or node.get('color_argb')),
                        horizontalAlignment=1 if node['classname']=='Button' else node.get('h_alignment',0),
                        verticalAlignment=1 if node['classname']=='Button' else node.get('v_alignment',0),
                        outlineEnabled=node.get('outline_enabled',False),outlineSize=node.get('outline_size',1),
                        outlineColor=rgba(node.get('outline_color_argb')),shadowEnabled=node.get('shadow_enabled',False),
                        shadowOffset=node.get('shadow_offset'),shadowColor=rgba(node.get('shadow_color_argb')),
                        textAuthority='authored-static-string-not-player-state')
                    if node['text'] in ('Button','button'):
                        item['previewExcludedReason']='button-authoring-placeholder'
                    if Path(layout).name=='Topbar_left_ext.csb' and node['classname']=='Text' and name=='title':
                        item.update(text=title['resolved_original_title'],authoredText=node['text'],
                            textAuthority='original-initTopUI-assign-MAIN_LINE_TITLE-static-source',
                            textSource=dict(path=str(TITLE),sha256=TITLE_SHA))
                    items.append(item)
            if node.get('project_path'):
                child=ui_path(node['project_path'])
                if child in stack or child==layout or child not in layouts:
                    raise ValueError('Missing or recursive original ProjectNode')
                visit(layouts[child],child,node_id,world,visible,opacity,full_path+['@'+Path(child).stem],clips,
                      reason,stack+(layout,))
            for _,child in children:
                if child.get('z_order',0)>=0:
                    visit(child,layout,node_id,world,visible,opacity,full_path,clips,reason,stack)
        visit(layouts[entry],entry,None,[1,0,0,1,0,0],True,1,[],[])
        for item in items:
            index={n['id']:n for n in nodes}
            item['clipGeometry']=[index[key]['clipGeometry'] for key in item['clipNodeIds']]
        return dict(entry=entry,nodes=nodes,sourceDrawItems=items,
                    items=[i for i in items if i['visible'] and i['opacity']>0 and not i['previewExcludedReason']],
                    controls=controls,gaps=gaps)
    page=convert(ENTRY)
    templates={Path(path).stem:convert(path) for path in layouts
               if Path(path).name in ('ChaperItem_Current_ext.csb','ChaperItem_Passed_ext.csb','ChapterItem_Locked_ext.csb')}
    # No template instance is injected into the original empty scroll container.
    scroll=[n for n in page['nodes'] if n['classname']=='ScrollView']
    if len(scroll)!=1 or layouts[ENTRY]['name']!='Layer':
        raise ValueError('Unexpected original worldline container')
    evidence=json.loads(REA.read_text('utf8'))
    rea_ids=[row['evidence_id'] for row in evidence['records']
             if row.get('subject',{}).get('digest',{}).get('sha256')==APK_SHA256]
    result=dict(schemaVersion=1,canvas=dict(width=1280,height=720,drawOrigin='top-left',sourceOrigin='bottom-left'),
        apkSha256=APK_SHA256,entry=ENTRY,backgroundAuthority='authored-BeforeTen-static-design; no-local-chapter-binding',
        page=page,templates=templates,sprites=sprites,fonts=fonts,sources=sources,
        progressBinding=dict(available=False,chapterInstances=0,reason='Node API has no original chapter progress state',
            originalScrollViewNodeId=scroll[0]['id'],templateStateMustNotBeInferred=True,
            tutorialIsNotMainlineChapter=True),
        evidence=dict(reaArchiveEvidenceIds=rea_ids,reaBundleSha256=digest(REA),dependencyReportSha256=digest(report_path),
            spriteReportSha256=digest(PIXELS),schemaSha256=digest(SCHEMA),
            titleLocalizationSha256=TITLE_SHA,layoutEvidenceKind='ordinary-tool-static-CSB-conversion'),
        limitations=['No original-client execution, timeline playback or chapter runtime binding',
            'Original authoring canvas is 1280x720; responsive constraints are retained, not evaluated',
            'Chapter templates are preserved source definitions only; runtime does not render fake current/passed/locked rows',
            'Original page background remains the authored BeforeTen static view, not evidence of selected-profile progress',
            'Currency toolbar, branch notifications and unconverted emitters are omitted; title uses original MAIN_LINE_TITLE binding',
            'Local battle preview is a separate reconstruction adapter, not an original worldline chapter'])
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'layout.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    summary=dict(schemaVersion=1,layoutSha256=digest(OUT/'layout.json'),sourceLayouts=len(sources),
        pageNodes=len(page['nodes']),pageDrawItems=len(page['items']),pageDrawKinds=dict(Counter(i['kind'] for i in page['items'])),
        sprites=len(sprites),fonts=len(fonts),chapterTemplates=len(templates),chapterInstances=0,
        progressAvailable=False,controls=page['controls'])
    (OUT/'report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf8')
    return summary


def render_reference():
    from PIL import Image,ImageDraw,ImageFont
    layout=json.loads((OUT/'layout.json').read_text('utf8'))
    images={r['id']:Image.open(r['png']).convert('RGBA') for r in layout['sprites']}
    fonts={r['id']:r['ttf'] for r in layout['fonts']}
    canvas=Image.new('RGBA',(1280,720),(0,0,0,255))
    for item in layout['page']['items']:
        w,h=[max(1,round(v)) for v in item['size']]
        if item['kind']=='sprite':
            pixels=images[item['spriteId']].copy().resize((w,h),Image.Resampling.LANCZOS)
            if item['flipX']:pixels=pixels.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if item['flipY']:pixels=pixels.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        elif item['kind']=='text':
            pixels=Image.new('RGBA',(w,h))
            painter=ImageDraw.Draw(pixels)
            font=ImageFont.truetype(fonts[item['fontId']],max(1,item['fontSize']))
            bbox=painter.textbbox((0,0),item['text'],font=font)
            tw,th=bbox[2]-bbox[0],bbox[3]-bbox[1]
            x=[0,(w-tw)/2,w-tw][item['horizontalAlignment']]-bbox[0]
            y=[0,(h-th)/2,h-th][item['verticalAlignment']]-bbox[1]
            painter.text((x,y),item['text'],font=font,fill=tuple(round(v*255) for v in item['color']))
        else:continue
        channels=pixels.split()
        if item['kind']=='sprite':
            pixels=Image.merge('RGBA',[channels[i].point(lambda x,f=item['color'][i]:round(x*f)) for i in range(4)])
        pixels.putalpha(pixels.getchannel('A').point(lambda x:round(x*item['opacity'])))
        a,b,c,d,x,y=item['geometry']['matrix']
        determinant=a*d-b*c
        if abs(determinant)<1e-12:continue
        inverse=[d/determinant,-c/determinant,(c*y-d*x)/determinant,
                 -b/determinant,a/determinant,(b*x-a*y)/determinant]
        layer=pixels.transform(canvas.size,Image.Transform.AFFINE,inverse,resample=Image.Resampling.BICUBIC)
        canvas=Image.alpha_composite(canvas,layer)
    canvas.convert('RGB').save(OUT/'reference-static-page.png')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render-reference',action='store_true')
    args=parser.parse_args()
    print(json.dumps(build(),ensure_ascii=False))
    if args.render_reference:render_reference()
