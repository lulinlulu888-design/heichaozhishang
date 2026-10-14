"""Generate a bounded evidence-based hero/hall progress baseline, without estimates."""
import json
from pathlib import Path
from extract_game_data import export_table

ROOT=Path(__file__).resolve().parents[1]

def main():
    table=export_table(8995)
    heroes=[r for r in table['rows'] if r['fields'].get('UseRole')==1]
    if len(heroes)!=35:raise ValueError('Hero roster changed; review scope')
    lines=['# 角色恢复进度与燃尽记录','',
        '统计范围：本 APK 中 35 条 UseRole=1 英雄配置。每位按六项验收：模型、贴图参考、待机、完整基础动作、大招演出、完整战斗接入。模型/贴图参考完成不等于原材质复原；部分接入不计完整完成。','',
        '| ID | 英雄 | 模型 | 贴图参考 | 待机 | 基础动作 | 大招演出 | 战斗接入 |',
        '|---:|---|---|---|---|---|---|---|']
    for r in heroes:
        i=r['id'];name=r['fields']['NAME']
        states=['待核验']*6
        if i==1:states=['已验证','已验证','已验证','部分恢复','待恢复','单人试玩']
        if i==2:states=['已验证','已验证','已验证','已提取未播放','已提取未播放','待接入']
        if i==33:states=['已验证','已验证','已验证','待核验','待恢复','大厅展示']
        if i==3:states=['待核验','立绘样本','待核验','待核验','待核验','待接入']
        lines.append('| '+str(i)+' | '+name+' | '+' | '.join(states)+' |')
    lines += ['', '已验证依据：艾尔莎见 docs/elsa-model-conversion.md、docs/battle-idle.md、docs/battle-visual-recovery.md；琳见 docs/lynn-recovery.md。其他英雄本轮仅完整读取角色配置，尚未逐角色做模型/动作验收，不将“待核验”解释为资源缺失。', '',
        '## 大厅优先验收清单','',
        '- [x] 原场景身份：场景表203，HallSceneHome，midgard_home_3d。',
        '- [x] 环境模型与颜色贴图导出：79份网格、116实例、61纹理。',
        '- [x] 浏览器实际显示与原镜头参数载入（原渲染器方向一致性仍待验证）。',
        '- [ ] 原大厅UI图集、按钮和布局。',
        '- [ ] 大厅角色及互动动作。',
        '- [ ] 原材质、灯光、反射和特效。',
        '- [ ] 共享Cocos大厅接入与存档入口。',
        '- [ ] 最新四平台构建和大厅实机游玩。','',
        '## 燃尽基线','',
        '当前登记218项验收（35×6角色项＋8大厅项），完整通过12项，剩余206项。每项权重相同，仅用于跟踪验收数量；不是工时、开发完成百分比，也不包含整个项目所有需求。',
        '2026-10-14是首次建立此口径的真实记录。没有补造过去曲线，没有估算截止日期；后续通过验收时追加记录，范围变化单独登记。','',
        '| 记录日期 | 总项 | 完整通过 | 剩余 |', '|---|---:|---:|---:|','| 2026-10-14 基线 | 218 | 8 | 210 |','| 2026-10-14 不知火大厅显示 | 218 | 12 | 206 |','',
        '![燃尽基线](recovery-burndown.svg)','',
        '原生包仍需更新；macOS/iOS实际构建运行尚未通过。大招骨骼动作、镜头、特效、音效和战斗触发须分别验收。']
    (ROOT/'docs/recovery-progress.md').write_text('\n'.join(lines)+'\n','utf8')
    svg='''<svg xmlns="http://www.w3.org/2000/svg" width="800" height="300" viewBox="0 0 800 300"><rect width="800" height="300" fill="#101c29"/><g font-family="sans-serif" fill="#edf4fa"><text x="40" y="38" font-size="22">角色与大厅验收燃尽基线</text><text x="40" y="68" font-size="14">两条真实验收记录；未绘制预计完成曲线</text><path d="M90 100V240H740" stroke="#66778a" fill="none"/><text x="25" y="111">218</text><text x="55" y="244">0</text><path d="M240 105L570 108" stroke="#4ed7cf" stroke-width="3"/><circle cx="240" cy="105" r="6" fill="#4ed7cf"/><circle cx="570" cy="108" r="6" fill="#4ed7cf"/><text x="190" y="91">剩余210</text><text x="540" y="91">剩余206</text><text x="180" y="268">10月14日 基线</text><text x="500" y="268">不知火大厅显示</text><text x="90" y="290" font-size="12">三个英雄模型/颜色参考与待机共9项；大厅身份、导出、显示共3项</text></g></svg>'''
    (ROOT/'docs/recovery-burndown.svg').write_text(svg,'utf8')
    print(json.dumps(dict(heroes=len(heroes),total=218,passed=12,remaining=206)))

if __name__=='__main__':main()
