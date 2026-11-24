"""Test parsing of emitted gate connections and missing sequential inputs."""
import unittest
import ReadProbe as read


class ReadTests(unittest.TestCase):
    def test_connections_with_nested_constants_and_escaped_names(self):
        text = 'module Top; TpuIcb Bus (.Addr({4\'h9, {28{1\'b0}}}), .Size(), .Clock(clk)); endmodule'
        # DC puts emitted instances on their own line.
        text = text.replace(' TpuIcb', '\n TpuIcb')
        row = list(read.instances(text))[0]
        self.assertEqual(row[0:2], ('TpuIcb', 'Bus'))
        ports = read.bindings(row[2])
        self.assertEqual(ports['Addr'], "{4'h9, {28{1'b0}}}")
        self.assertEqual(ports['Size'], '')
        self.assertEqual(ports['Clock'], 'clk')

    def test_detects_power_or_reset_input_not_connected(self):
        model = 'module FF(Q,D,CP,RN,VDD,VSS); output Q; input D,CP,RN; input VDD,VSS; endmodule'
        self.assertEqual(read.input_names(model), ['D', 'CP', 'RN', 'VDD', 'VSS'])
        ports = read.bindings("(.Q(q), .D(d), .CP(clk), .RN(rst))")
        self.assertEqual([pin for pin in read.input_names(model) if not ports.get(pin)], ['VDD', 'VSS'])

    def test_module_boundary_does_not_include_other_designs(self):
        text = 'module A(input a); endmodule\nmodule B(input b); endmodule'
        self.assertIn('input b', read.module(text, 'B'))
        self.assertNotIn('input a', read.module(text, 'B'))


if __name__ == '__main__':
    unittest.main()
