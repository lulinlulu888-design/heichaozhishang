"""Quantify screen-side dependence on the unverified source camera convention."""
import json,hashlib
from pathlib import Path
import numpy as np
from export_elsa_model import split_glb
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/battle-visual/city-scenes'
def main():
    path=OUT/'city_battle_2/scene.glb';blob=path.read_bytes();doc,_=split_glb(blob)
    camera=doc['extras']['sourceCameras'][0]
    matrix=np.array([float(v) for v in camera['Transform'].split(',')]).reshape(4,4).T
    matrix[:3,:3]/=np.linalg.norm(matrix[:3,:3],axis=0)
    current=matrix@np.diag([-1.,1.,-1.,1.])
    client=ROOT/'clients/cocos-poc/assets/CitySceneView.ts'
    if 'this.frame.flipUVX = true;' not in client.read_text('utf8'):
        raise ValueError('Current projection-output correction is absent')
    players=json.loads((OUT/'player-placement/report.json').read_text('utf8'))['derived_slots']
    enemy=json.loads((OUT/'battle-placement/report.json').read_text('utf8'))['derived']
    points=[('player-slot-'+str(r['pos_index']),r['position']) for r in players]+[('enemy',enemy['position'])]
    rows=[]
    for name,pos in points:
        point=np.array([*pos,1.]);source=np.linalg.inv(matrix)@point;adapted=np.linalg.inv(current)@point
        if adapted[2]>=0:raise ValueError('Point not in front of current camera')
        rows.append(dict(name=name,world_position=pos,source_camera_local=source[:3].tolist(),
            current_camera_local=adapted[:3].tolist(),current_screen_side='left' if adapted[0]>0 else 'right',
            source_positive_z_with_positive_x_right_hypothesis='right' if source[0]>0 else 'left'))
    report=dict(source_glb_sha256=hashlib.sha256(blob).hexdigest(),camera=camera,
        current_adapter='Remove source uniform scale; postmultiply local Y180; flip complete RenderTexture output X',
        client_sha256=hashlib.sha256(client.read_bytes()).hexdigest(),points=rows,
        findings=['Current local Y180 conversion reverses both X and Z camera axes.',
            'Current output X correction restores allies left/enemies right without modifying source actor coordinates.',
            'User-supplied historical gameplay confirms that side layout; original native projection implementation remains unverified.'],
        limits=['No original renderer projection matrix or runtime capture validated.',
            'Do not flip actors alone: scene, projection handedness, culling and input targets must be treated consistently.',
            'No runtime/client change made by this audit.'])
    (OUT/'camera-side-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report))
if __name__=='__main__':main()
