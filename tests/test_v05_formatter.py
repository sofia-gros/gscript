import unittest
from gscript.formatter import format_source,semantic
from gscript import parse_code


class FormatterTests(unittest.TestCase):
    def test_comments_idempotence_and_semantics(self):
        source='// comment\nfunc add(a int,b int) int{return a+b}\nprintln(add(1,2)) // end\n'
        result=format_source(source)
        self.assertIn('  return a + b',result)
        self.assertIn('// comment',result);self.assertIn('// end',result)
        self.assertEqual(format_source(result),result)
        self.assertEqual(semantic(parse_code(source)),semantic(parse_code(result)))

    def test_all_existing_language_feature_cases(self):
        from test_extensions import CASES
        for name,(source,_) in CASES.items():
            with self.subTest(name=name):
                result=format_source(source)
                self.assertEqual(format_source(result),result)
