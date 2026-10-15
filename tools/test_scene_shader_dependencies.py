"""Literal dependency discovery must not invent shader search/branch results."""
import unittest

from audit_city_scene_dependencies import shader_includes


class ShaderIncludesTest(unittest.TestCase):
    def test_parent_and_resource_root_remain_candidates(self):
        rows = shader_includes(b'#include "../common.hlsl"\n#include <shader/shared.hlsl>',
                               'shader/built_in/materials/material.hlsl')
        self.assertEqual(rows[0]['candidates'], ['shader/built_in/common.hlsl'])
        self.assertEqual(rows[1]['candidates'], [
            'shader/built_in/materials/shader/shared.hlsl', 'shader/shared.hlsl'])
        self.assertEqual(rows[1]['line'], 2)
        self.assertIn('unresolved', rows[0]['conditionalSelection'])

    def test_comments_ignored_but_conditional_literals_retained(self):
        rows = shader_includes(b'/*\n#include "wrong.hlsl"\n*/\n// #include "wrong2.hlsl"\n'
                               b'#if SOMETHING\n#include "right.hlsl"\n#endif\n#include MACRO',
                               'shader/main.hlsl')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['line'], 6)
        self.assertEqual(rows[0]['candidates'], ['shader/right.hlsl'])

    def test_invalid_absolute_and_escape_paths_are_not_followed(self):
        rows = shader_includes(b'#include "../../../../secret.hlsl"\n#include "C:/secret.hlsl"\n'
                               b'#include "/shader/main.hlsl"', 'shader/main.hlsl')
        self.assertEqual([row['candidates'] for row in rows], [[], [], []])

    def test_windows_spelling_and_utf8_bom(self):
        rows = shader_includes(b'\xef\xbb\xbf#include "..\\common.hlsl"',
                               'shader/built_in/material.hlsl')
        self.assertEqual(rows[0]['candidates'], ['shader/common.hlsl'])

    def test_virtual_res_prefix_retains_original_and_explicit_candidate(self):
        rows = shader_includes(b'#include "res/shader/built_in/common.hlsl"',
                               'shader/built_in/materials/material.hlsl')
        self.assertEqual(rows[0]['original'], 'res/shader/built_in/common.hlsl')
        self.assertEqual(rows[0]['candidates'][-1], 'shader/built_in/common.hlsl')

    def test_leading_blank_lines_do_not_move_include_location(self):
        rows = shader_includes(b'\n\n  #include "a.hlsl"', 'shader/main.hlsl')
        self.assertEqual(rows[0]['line'], 3)


if __name__ == '__main__':
    unittest.main()
