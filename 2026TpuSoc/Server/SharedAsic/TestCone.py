"""Verify generated passive observers against escaped mapped identifiers."""
import unittest
import PrepareCone as cone

FF = 'module DQV0_12TR40(Q,CK,D); output Q; input CK,D; endmodule'
INV = 'module INV(I,ZN); input I; output ZN; endmodule'
BUS = r'''module TpuIcb(input Clock);
wire [2:0] State;
wire [1:0] Word;
wire n1,n2;
INV U1 (.I(Word[0]),.ZN(n1));
DQV0_12TR40 \Word_reg[0]  (.D(n1),.CK(Clock),.Q(Word[0]));
DQV0_12TR40 \Word_reg[1]  (.D(Word[0]),.CK(Clock),.Q(Word[1]));
DQV0_12TR40 \State_reg[0]  (.D(Word[1]),.CK(Clock),.Q(State[0]));
DQV0_12TR40 \State_reg[1]  (.D(State[0]),.CK(Clock),.Q(State[1]));
DQV0_12TR40 \State_reg[2]  (.D(State[1]),.CK(Clock),.Q(State[2]));
endmodule'''


class ConeTests(unittest.TestCase):
    def test_escaped_identifier_terminated_before_pin(self):
        self.assertEqual(cone.hierarchy(r'\Word_reg[0]', 'D'), r'GateIcbSmoke.Dut.\Word_reg[0] .D')

    def test_direction_and_observation(self):
        result = cone.observer(BUS, {'DQV0_12TR40': FF, 'INV': INV})
        self.assertIn('!$isunknown({GateIcbSmoke.Dut.U1.I})', result)
        self.assertIn('$isunknown(GateIcbSmoke.Dut.U1.ZN)', result)
        self.assertIn(r'GateIcbSmoke.Dut.\Word_reg[1] .D', result)
        self.assertNotIn('force ', result)
        self.assertNotIn('assign GateIcbSmoke', result)


if __name__ == '__main__':
    unittest.main()
