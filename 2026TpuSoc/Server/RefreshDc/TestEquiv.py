"""Acceptance and exact incremental-change gates; not a hardware equivalence test."""
import unittest
import Equiv


class EquivTest(unittest.TestCase):
    def changes(self):
        result = []
        for region, ref, count in [('outside','BUFV32_12TR40',1),('outside','BUFV32RD_12TR40',50),
            ('outside','BUFV32RQ_12TR40',10),('sram','BUFV24RQ_12TR40',8),('sram','BUFV32_12TR40',16),
            ('sram','BUFV32RQ_12TR40',144),('sram','DEL4V0_12TR40',128)]:
            result += [{'region':region,'kind':'added','before':'','after':ref} for _ in range(count)]
        return result

    def test_exact_357_additions(self):
        changes = self.changes()
        self.assertEqual(len(changes),357)
        Equiv.validate_changes(changes)
        changes[0]['kind']='removed'
        with self.assertRaises(ValueError):
            Equiv.validate_changes(changes)

    def test_missing_addition_rejected(self):
        with self.assertRaises(ValueError):
            Equiv.validate_changes(self.changes()[1:])

    def test_native_verify_and_unchanged_inputs_required(self):
        status={'MATCH_RETURN':['1'],'VERIFY_RETURN':['1'],
                'RESULT':['HOLD_NETLIST_TOOL_VERIFY_TRUE_BOUNDARY_REVIEW_PENDING']}
        self.assertTrue(Equiv.accepted(0,True,status,''))
        self.assertFalse(Equiv.accepted(0,False,status,''))
        self.assertFalse(Equiv.accepted(2,True,status,''))
        self.assertFalse(Equiv.accepted(0,True,status,'Error: fixture'))
        status['VERIFY_RETURN']=['0']
        self.assertFalse(Equiv.accepted(0,True,status,''))


if __name__=='__main__':
    unittest.main()
