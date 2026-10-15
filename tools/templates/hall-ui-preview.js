// Source-authored CSB layout reference. Never executes game scripts or simulates account state.
export async function mountHallUI({localState=false,apiPort=7460}={}) {
  const [layoutResponse, spriteResponse] = await Promise.all([
    fetch('./ui/layout.json'), fetch('./ui/sprites.json'),
  ]);
  if (!layoutResponse.ok || !spriteResponse.ok) throw Error('大厅 UI 资源未准备');
  const layouts = await layoutResponse.json(), sprites = await spriteResponse.json();
  const fontResponse=await fetch('./ui/fonts.json');
  if(!fontResponse.ok)throw Error('大厅原字体清单缺失');
  const fontMap=new Map();
  for(const row of await fontResponse.json()){
    const font=new FontFace(row.family,`url(./ui/${row.file})`);
    await font.load();document.fonts.add(font);fontMap.set(row.path,row.family);
  }
  let trees = new Map(layouts.layouts.map(row => [row.path, row.tree]));
  const pictures = new Map(await Promise.all(sprites.map(async row => {
    const img = new Image(); img.src = './ui/'+row.file; await img.decode();
    return [row.plist+'\0'+row.source_frame, img];
  })));
  const canvas = document.createElement('canvas'); canvas.id = 'hall-source-ui';
  canvas.style.cssText = 'pointer-events:none;transform:translate(-50%,-50%);z-index:1';
  document.body.append(canvas);
  const context = canvas.getContext('2d');
  const skipped = new Map();
  function skip(reason) { skipped.set(reason, (skipped.get(reason)||0)+1); }
  function draw(node, depth=0) {
    if (!node || depth>80) throw Error('大厅 UI 引用层级异常');
    if (node.options_status) { skip('unknown '+node.classname); return; }
    if (!node.visible || node.alpha===0) return;
    context.save();
    const [x,y]=node.position||[0,0], [sx,sy]=node.scale||[1,1];
    const [ax,ay]=node.anchor||[0,0], [w,h]=node.size||[0,0];
    const [rx,ry]=node.rotation_skew||[0,0];
    // Cocos clockwise rotationSkew is expressed in a bottom-left coordinate system.
    const radians=Math.PI/180;
    context.translate(x,y);
    context.transform(Math.cos(ry*radians)*sx,-Math.sin(ry*radians)*sx,
      Math.sin(rx*radians)*sy,Math.cos(rx*radians)*sy,0,0);
    context.translate(-ax*w,-ay*h);
    context.globalAlpha *= node.alpha/255;
    const resource=node.resource;
    if (resource?.plist) {
      const path=resource.plist.startsWith('uires/')?resource.plist:'uires/'+resource.plist;
      const img=pictures.get(path+'\0'+resource.path);
      if(img) {
        context.save();
        if(node.classname==='LoadingBar') {
          const fraction=Math.max(0,Math.min(100,node.percent))/100;
          context.beginPath();context.rect(node.direction===1?w*(1-fraction):0,0,w*fraction,h);context.clip();
        }
        context.translate(node.flip_x?w:0,node.flip_y?0:h);
        context.scale(node.flip_x?-1:1,node.flip_y?1:-1);
        context.drawImage(img,0,0,w||img.width,h||img.height);context.restore();
      } else skip('unresolved sprite');
    }
    if((node.classname==='Text'||node.classname==='Button') && node.text) {
      const color=node.text_color_argb||node.color_argb||[255,255,255,255];
      context.save();context.scale(1,-1);
      context.fillStyle=`rgb(${color[1]},${color[2]},${color[3]})`;
      const fontPath=node.font_resource?.path;
      const family=fontPath?fontMap.get(fontPath.startsWith('uires/')?fontPath:'uires/'+fontPath):null;
      context.font=`${node.font_size||20}px ${family||'system-ui'}`;
      const horizontal=node.classname==='Button'?1:node.h_alignment||0;
      const vertical=node.classname==='Button'?1:node.v_alignment||0;
      context.textAlign=['left','center','right'][horizontal];
      context.textBaseline=['top','middle','bottom'][vertical];
      context.fillText(node.text,[0,w/2,w][horizontal],[-h,-h/2,0][vertical]);context.restore();
    }
    if(node.project_path) {
      const path=node.project_path.startsWith('uires/')?node.project_path:'uires/'+node.project_path;
      const tree=trees.get(path);if(tree)draw(tree,depth+1);else skip('missing project');
    }
    for(const child of [...node.children].sort((a,b)=>(a.z_order||0)-(b.z_order||0)))draw(child,depth+1);
    context.restore();
  }
  function render() {
    const width=Math.min(innerWidth,innerHeight*16/9),height=width*9/16,dpr=Math.min(devicePixelRatio,2);
    canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);
    canvas.style.width=width+'px';canvas.style.height=height+'px';
    context.setTransform(canvas.width/1280,0,0,-canvas.height/720,0,canvas.height);
    skipped.clear();draw(trees.get(layouts.entry));
    canvas.dataset.skipped=JSON.stringify(Object.fromEntries(skipped));
    canvas.dataset.mode=localState?'local-reconstruction-profile':'source-authored-static-layout';
  }
  if(localState) {
    const {listHallProfiles,createHallLocalState,applyHallLocalState}=await import('./hall-local-state.js');
    let profiles=[];
    const panel=document.createElement('div');panel.id='hall-profiles';
    const label=document.createElement('label');label.textContent='本地档案 ';label.htmlFor='hall-profile';
    const select=document.createElement('select');select.id='hall-profile';
    const reload=document.createElement('button');reload.textContent='重新读取';
    const message=document.createElement('output');message.setAttribute('aria-live','polite');
    panel.append(label,select,reload,message);document.body.append(panel);
    function options() {
      select.replaceChildren(new Option('请选择本地档案',''));
      for(const p of profiles)select.add(new Option(p.displayName,p.id));
      select.value='';
    }
    function apply() {
      const state=createHallLocalState(profiles,select.value||null);
      const patched=applyHallLocalState(layouts,state);
      trees=new Map(patched.layouts.map(row=>[row.path,row.tree]));
      canvas.setAttribute('aria-label',state.profile?'本地档案：'+state.profile.displayName:'尚未选择本地档案');
      render();
    }
    async function load() {
      reload.disabled=true;select.disabled=true;message.textContent='读取中…';
      // Clearing selection avoids displaying stale names after a failed refresh.
      profiles=[];options();apply();
      try {
        profiles=await listHallProfiles(apiPort,{signal:AbortSignal.timeout(5000)});
        options();message.textContent=profiles.length?'仅显示姓名；成长与活动待恢复':'暂无本地档案';
      } catch(error) {message.textContent=error.message;}
      finally {reload.disabled=false;select.disabled=false;}
    }
    select.onchange=()=>{try{apply();}catch(error){message.textContent=error.message;}};
    reload.onclick=load;await load();
  }
  render();addEventListener('resize',render);
  return canvas;
}
