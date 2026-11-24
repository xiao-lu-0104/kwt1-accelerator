import csv
import json
from pathlib import Path
import tempfile
import unittest
from PinPlan import plan, validate


def fixture(d):
    (d / 'DieBoundary.txt').write_text('0 0 2100 2100')
    ports = ['clk', 'rst_n', 'test_mode', 'core_csr_clk', 'inspect_core_clk']
    for bus in ('ext2itcm_icb_cmd_wdata', 'ext2dtcm_icb_rsp_rdata', 'mem_icb_cmd_addr',
                'ppi_icb_rsp_rdata', 'clint_icb_cmd_wdata', 'plic_icb_cmd_addr', 'inspect_pc', 'dpc_r'):
        ports.extend(bus+'['+str(i)+']' for i in range(32))
    (d / 'PortInventory.tsv').write_text('port\tdirection\n'+''.join(p+'\tin\n' for p in reversed(ports)))
    return ports


def terminals(d, pins):
    with (d / 'PortTerminalGeometry.tsv').open('w') as f:
        w = csv.DictWriter(f, fieldnames=['port', 'terminal', 'x1', 'y1', 'x2', 'y2', 'layers'], delimiter='\t', lineterminator='\n')
        w.writeheader()
        for p in pins:
            w.writerow({'port': p['port'], 'terminal': p['port'], 'x1': p['x']-.035, 'x2': p['x']+.035,
                        'y1': p['y']-.035, 'y2': p['y']+.035, 'layers': p['layer']})


class Plan(unittest.TestCase):
    def test_all_ports_once_grouped_bus_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp); ports=fixture(d); data=plan(d); pins=data['pins']
            self.assertEqual(set(ports), {p['port'] for p in pins})
            for bus in ('ext2itcm_icb_cmd_wdata', 'inspect_pc'):
                b=[p for p in pins if p['port'].startswith(bus+'[')]
                self.assertEqual([p['port'] for p in b], [bus+'['+str(i)+']' for i in range(32)])
                self.assertEqual(len({p['side'] for p in b}), 1)
            terminals(d, pins)
            self.assertEqual(validate(d)['port_count'], len(ports))

    def invalid(self, change):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp); fixture(d); pins=plan(d)['pins']; change(pins); terminals(d, pins)
            with self.assertRaises(ValueError): validate(d)
            self.assertFalse((d/'IoValidation.json').exists())

    def test_missing_terminal_rejected(self): self.invalid(lambda pins: pins.pop())
    def test_duplicate_terminal_rejected(self): self.invalid(lambda pins: pins.append(pins[0].copy()))
    def test_wrong_layer_rejected(self): self.invalid(lambda pins: pins[0].update(layer='M7'))
    def test_far_away_terminal_rejected(self): self.invalid(lambda pins: pins[0].update(x=pins[0]['x']+4))
    def test_overlarge_pin_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp); fixture(d); data=plan(d); terminals(d,data['pins'])
            path=d/'PortTerminalGeometry.tsv'
            with path.open() as f:
                rows=list(csv.DictReader(f,delimiter='\t'))
            # Extend the first shape over the next shape while preserving its center.
            first=data['pins'][0]; axis='y' if first['side'] in ('left','right') else 'x'
            rows[0][axis+'1']=str(first[axis]-first['pitch_um']*2)
            rows[0][axis+'2']=str(first[axis]+first['pitch_um']*2)
            with path.open('w') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t');w.writeheader();w.writerows(rows)
            with self.assertRaises(ValueError): validate(d)

    def test_duplicate_inventory_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);fixture(d)
            with (d/'PortInventory.tsv').open('a') as f:f.write('clk\tin\n')
            with self.assertRaises(ValueError):plan(d)

    def test_overfull_side_rejected_without_splitting_interface(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);fixture(d);(d/'DieBoundary.txt').write_text('0 0 41 41')
            with self.assertRaises(ValueError):plan(d)


if __name__ == '__main__': unittest.main()
