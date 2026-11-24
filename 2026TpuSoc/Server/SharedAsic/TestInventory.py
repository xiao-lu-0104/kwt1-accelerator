"""Check mapped hierarchy inventory, escaped names and unsupported sequential guards."""
import unittest
import PrepareInventory as inv

FF_MODEL = 'module DQV0_12TR40(Q,CK,D); output Q; input CK,D; udp_dff I0(Q,D,CK); endmodule'
TOP = '''module e203_subsys_nice_core;
TpuIcb Bus (.Clock(nice_clk),.ResetN(nice_rst_n));
endmodule'''
BUS = r'''module TpuIcb;
DQV0_12TR40 \Word_reg[0]  (.D(n552),.CK(Clock),.Q(Word[0]));
DQV0_12TR40 \Word_reg[1]  (.D(1'b0),.CK(Clock),.Q(Word[1]));
DQV0_12TR40 \State_reg[0]  (.D(1'b0),.CK(Clock),.Q(State[0]));
DQV0_12TR40 \State_reg[1]  (.D(1'b0),.CK(Clock),.Q(State[1]));
DQV0_12TR40 \State_reg[2]  (.D(1'b0),.CK(Clock),.Q(State[2]));
endmodule'''


class InventoryTests(unittest.TestCase):
    def test_nested_escaped_hierarchy_and_reset_only_seeding(self):
        rows, opaque = inv.inventory({'e203_subsys_nice_core': TOP, 'TpuIcb': BUS}, {'DQV0_12TR40': FF_MODEL})
        self.assertEqual(len(rows), 5)
        self.assertFalse(opaque)
        source, controls = inv.monitor(rows)
        self.assertEqual(len(controls), 5)
        self.assertIn(r'\Word_reg[0] .Q', source)
        self.assertEqual(source.count('release '), 6)  # one word-only branch, five all-FF releases
        self.assertIn('RESET_INVENTORY: total_FF=5', source)

    def test_unmapped_procedural_state_not_silently_skipped(self):
        with self.assertRaisesRegex(ValueError, 'Procedural candidate'):
            inv.inventory({'e203_subsys_nice_core': TOP, 'TpuIcb': BUS.replace('endmodule','always @(posedge Clock) X<=D; endmodule')}, {'DQV0_12TR40': FF_MODEL})

    def test_unknown_sequential_ports_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Sequential models not covered'):
            inv.inventory({'e203_subsys_nice_core': TOP, 'TpuIcb': BUS}, {'DQV0_12TR40': FF_MODEL.replace('input CK,D;', 'input CKN,D;')})


if __name__ == '__main__':
    unittest.main()
