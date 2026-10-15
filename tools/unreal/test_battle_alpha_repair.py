"""Source/native-graph contract tests, ordinary Python; never imports Unreal."""
import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from repair_battle_alpha import repair_plan,graph_semantics,BASE

class AlphaRepairContract(unittest.TestCase):
 def setUp(self):self.graph=json.loads((BASE/'native-audit.json').read_text('utf8'))['material_graphs'][0]
 def test_real_graph_plan_preserves_zero_scalar_and_only_four_slots(self):
  plan=repair_plan()
  self.assertEqual([(r['component_slot'],r['source_slot'])for r in plan['slots']],[(1,2),(2,1),(4,7),(8,4)])
  self.assertEqual(plan['semantics']['scalar_to_preserve'],0)
  self.assertAlmostEqual(plan['semantics']['base_clip_to_restore'],100/255)
  self.assertFalse(plan['visual_verified']);self.assertFalse(plan['original_neox_shader_verified'])
 def test_missing_nested_graph_does_not_count_as_semantic_success(self):
  graph=copy.deepcopy(self.graph);graph['warnings']=[{'unavailable':'function_outputs'}]
  with self.assertRaises(ValueError):graph_semantics(graph)
 def test_alpha_channel_subtraction_and_root_binding_are_not_guessable(self):
  for name,edit in [
   ('MaterialExpressionMultiply_5',lambda n:n.update(input_output_names=['','RGB'])),
   ('MaterialExpressionSubtract_1',lambda n:n.update(inputs=list(reversed(n['inputs'])))),
   ('MaterialExpressionScalarParameter_0',lambda n:n.update(default_value=.5))]:
   graph=copy.deepcopy(self.graph);node=next(n for n in graph['nodes']if n['path'].endswith(':'+name));edit(node)
   with self.assertRaises(ValueError):graph_semantics(graph)
 def test_restore_once_matches_mask_boundary_but_double_restore_would_not(self):
  cutoff=100/255
  for alpha in [0,.2,cutoff-1e-7,cutoff,cutoff+1e-7,.5,.9,1]:
   intended=alpha>=cutoff
   repaired=max(0,min(1,alpha))-0-cutoff>=0
   self.assertEqual(repaired,intended)
  self.assertTrue(.5>=cutoff)
  self.assertFalse(.5-cutoff-cutoff>=0)

if __name__=='__main__':unittest.main()
