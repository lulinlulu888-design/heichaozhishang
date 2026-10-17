import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import audit_future_clip_triggers as audit

GIM = """<?xml version="1.0" encoding="gb18030"?>
<NeoX>
<Sockets>
<Socket Name="fx_center" BindType="7" MatrixToBone="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1" MustShow="false"/>
</Sockets>
<Triggers>
<shield_1><fx_hudun><trigger SocketName="fx_center" ObjectFileName="effects\\player\\future\\future_buff_2.sfx" Spark="UnControlledStart"/></fx_hudun></shield_1>
<buff_2><fx_buff2><trigger SocketName="fx_center" ObjectFileName="effects/player/future/future_buff_2.sfx" Spark="Start"/></fx_buff2></buff_2>
<show><event_0><trigger SocketName="fx_center" ObjectFileName="effects/player/future/show.sfx" Spark="Start"/></event_0></show>
</Triggers>
</NeoX>
""".encode('gb18030')


class FutureClipTriggerTest(unittest.TestCase):
    def test_prologue_clips_name_the_same_effect_without_a_bone(self):
        found = audit.clip_triggers(GIM)
        self.assertEqual(set(found), {'shield_1', 'buff_2'})
        self.assertEqual(found['shield_1']['spark'], 'UnControlledStart')
        self.assertEqual(found['buff_2']['spark'], 'Start')
        self.assertTrue(all(row['sfx'] == 'effects/player/future/future_buff_2.sfx' and row['boneName'] is None
                            and row['bindType'] == '7' for row in found.values()))

    def test_a_missing_trigger_is_rejected(self):
        broken = GIM.replace(b'<buff_2>', b'<unused>').replace(b'</buff_2>', b'</unused>')
        with self.assertRaises(ValueError):
            audit.clip_triggers(broken)


if __name__ == '__main__':
    unittest.main()
