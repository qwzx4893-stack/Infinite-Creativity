import io
import json
import unittest
from infinite_creativity.network import icon_inventory

class StreamingTests(unittest.TestCase):
    def test_retains_names_and_license_but_drops_svg_and_aliases(self):
        data={'prefix':'sample','info':{'license':{'spdx':'MIT','url':'https://example.com/LICENSE'}},'icons':{'home':{'body':'<path/>'},'hidden':{'body':'<path/>','hidden':True}},'aliases':{'home-alias':{'parent':'home'}}}
        result=icon_inventory(io.BytesIO(json.dumps(data).encode()))
        self.assertEqual(set(result['icons']),{'home'})
        self.assertEqual(result['info']['license']['spdx'],'MIT')
        self.assertNotIn('body',json.dumps(result))

if __name__=='__main__': unittest.main()
