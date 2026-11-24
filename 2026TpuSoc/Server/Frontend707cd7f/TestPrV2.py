"""New collector source isolation/IO audit tests with fake ICC2; no native claims."""
import unittest
from BuildPrV2 import build_files
from TestPrFlow import Pr

EXTRA = '''
import sys
sys.path.insert(0,str(p.parent/'tools'))
from PinPlan import plan
(p/'DieBoundary.txt').write_text('0 0 2050 2050')
ports=['clk','rst_n']+['mem_icb_cmd_wdata['+str(i)+']' for i in range(128)]
(p/'PortInventory.tsv').write_text('port\\tdirection\\n'+''.join(n+'\\tin\\n' for n in ports))
data=plan(p)
rows=['port\\tterminal\\tx1\\ty1\\tx2\\ty2\\tlayers']
for pin in data['pins']:
    x,y=pin['x'],pin['y']
    if os.environ['MODE']=='bad_io':x+=10
    rows.append('%s\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s'%(pin['port'],pin['port'],x-.035,y-.035,x+.035,y+.035,pin['layer']))
(p/'PortTerminalGeometry.tsv').write_text('\\n'.join(rows)+'\\n')
'''


class PrV2(Pr):
    def case(self, mode='ok'):
        return super().case(mode,files_builder=build_files,fake_extra=EXTRA)

    def test_native_success_marker_does_not_bypass_bad_io(self):
        code,log=self.case('bad_io')
        self.assertNotEqual(code,0,log)
        self.assertIn('Native pin moved from planned location',log)


if __name__ == '__main__':
    unittest.main(defaultTest='PrV2')
