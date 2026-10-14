import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from trace_city_battle_placement import literal_assignments
from trace_first_encounter import inventory
import inspect_battle_rules as static

class CitySpawnLiterals(unittest.TestCase):
    def setUp(self):
        self.module=static.read_module(inventory()[407])

    def test_original_preset_five_has_explicit_transform(self):
        data=literal_assignments(self.module)['data']
        self.assertEqual(len(data),28)
        self.assertEqual(data[5][0],{'pos':[-21.96,-9.08,-40.1],'rot':[0,1.57,0]})

    def test_rejects_a_call_instead_of_assignment(self):
        code=bytearray(self.module['bytecode'])
        assignment=next(i for i in static.instructions(self.module) if i['opcode']==0x91)
        code[assignment['offset']]=0x83
        with self.assertRaisesRegex(ValueError,'Nonliteral opcode'):
            literal_assignments(dict(self.module,bytecode=bytes(code)))

    def test_rejects_duplicate_map_key(self):
        code=bytearray(self.module['bytecode'])
        loads=[i for i in static.instructions(self.module) if i['opcode']==0x99 and i.get('operand') in ('pos','rot')]
        code[loads[1]['offset']+1:loads[1]['end_exclusive']]=code[loads[0]['offset']+1:loads[0]['end_exclusive']]
        with self.assertRaisesRegex(ValueError,'duplicate map key'):
            literal_assignments(dict(self.module,bytecode=bytes(code)))

if __name__=='__main__':unittest.main()
