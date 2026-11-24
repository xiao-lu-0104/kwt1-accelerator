"""Check hierarchical SAIF unknown accounting and read-only provenance guards."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from ReviewTaskPower import ROOT, saif_review, select


def wrap(body):
    text='(SAIFILE (TIMESCALE 1 ps) (DURATION 100) '
    text+=''.join('(INSTANCE '+item+' ' for item in ROOT)
    return text+body+')'*len(ROOT)+')'


class PowerReviewTests(unittest.TestCase):
    def test_comments_bom_and_comment_like_quoted_identifiers(self):
        clean=wrap('(NET ("a//b" (TX 100) (TC 1)))')
        decorated='\ufeff/* VCS header (TX 999) unmatched ) */\n// comment with (TX 888)\n'+clean.replace(
            '(DURATION 100)','(DURATION /* units comment */ 100)').replace(
            '(TX 100)','(TX // a comment inside a statistic\n 100)')+'\n// trailer ( ignored\n'
        review=saif_review(decorated,{})
        self.assertEqual(review['TX_records'],1)
        self.assertEqual(review['nonzero_TX_records'],1)
        self.assertEqual(review['unknown'][0]['signal'],'a//b')
        self.assertEqual(review['ignored_comments'],5)

    def test_unknown_outside_text_is_not_silently_skipped(self):
        with self.assertRaisesRegex(ValueError,r'offset=0 line=1 column=1.*unexpected'):
            saif_review('unexpected banner\n'+wrap('(NET (a (TX 0)))'),{})
        with self.assertRaisesRegex(ValueError,'Unterminated SAIF block comment'):
            saif_review(wrap('(NET (a (TX 0)))')+' /* broken',{})
        with self.assertRaisesRegex(ValueError,'Multiple SAIF root'):
            saif_review(wrap('(NET (a (TX 0)))')+wrap('(NET (a (TX 0)))'),{})

    def test_unknowns_keep_conditional_records_and_leaf_scope(self):
        leaves={ROOT+('q_reg[0]',):{'ref':'DQV0_12TR40'}}
        body=r'''(NET (nice_clk (T0 50) (T1 50) (TX 0) (TC 20)))
(INSTANCE "DQV0_12TR40" q_reg\[0\]
  (PORT (Q (T0 0) (T1 0) (TX 100) (TC 0)))
  (NET (n0 (T0 0) (T1 0) (TX 100) (TC 0)))
  (NET (data (COND a (TX 10)) (COND b (TX 5)) (TC 1))))'''
        review=saif_review(wrap(body),leaves)
        self.assertEqual(review['TX_records'],5)
        self.assertEqual(review['nonzero_TX_records'],4)
        self.assertEqual(review['unknown_signals'],3)
        self.assertEqual(review['unknown'][0]['category'],'mapped_ff_output')
        self.assertEqual(review['unknown'][1]['category'],'library_model_internal')
        self.assertEqual(review['unknown'][0]['TX_fraction'],1)
        self.assertAlmostEqual(review['duration_seconds'],1e-10)
        self.assertEqual(review['clock_examples'][0]['stats']['TC'],20)

    def test_reject_truncation_and_unattributed_unknowns(self):
        with self.assertRaises(ValueError): saif_review(wrap('(NET (a (TX 0)))')[:-1],{})
        with self.assertRaises(ValueError): saif_review(wrap('(TX 5)'),{})

    def test_unknown_ports_are_not_waived_as_unused(self):
        leaves={ROOT+('mem',):{'ref':'RAMSP1024X16'}}
        review=saif_review(wrap('(INSTANCE mem (PORT (Q\\[0\\] (TX 100) (TC 0))))'),leaves)
        self.assertEqual(review['unknown'][0]['category'],'private_sram_port')
        self.assertEqual(review['unknown'][0]['signal'],'Q[0]')
        self.assertIn('no unknown waived',review['acceptance'])

    def test_changed_frozen_input_rejects_old_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=root/'candidate.v'
            source.write_text('original')
            record={'inputs':{str(source):hashlib.sha256(source.read_bytes()).hexdigest()}}
            (root/'TaskPowerInputs.json').write_text(json.dumps(record))
            source.write_text('changed')
            with self.assertRaisesRegex(ValueError,'Frozen input changed'): select(root)


if __name__=='__main__': unittest.main()
