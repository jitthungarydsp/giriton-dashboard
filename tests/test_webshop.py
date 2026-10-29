import ast
import unittest
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from types import SimpleNamespace
import importlib.util
spec = importlib.util.spec_from_file_location('webshop_validation', Path(__file__).resolve().parents[1]/'resources/webshop.py')
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)
validate_webshop_product = validation.validate_webshop_product
validate_webshop_items = validation.validate_webshop_items


class ApiError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code


class WebshopTest(unittest.TestCase):
    def test_variant_and_custom_attribute_validation(self):
        variant = dict(sku='POLO-M', price_huf=4500, size='M', type='Rövid ujjú', attributes={'Szín': 'Zöld'})
        attributes = [dict(name='Szín', values=['Zöld'], required=True)]
        validate_webshop_product({'name':'Póló'}, [variant], attributes)
        for changes in [{'price_huf':4500.5}, {'price_huf':True}, {'sku':' '}, {'attributes':{}}, {'attributes':{'Szín':'Piros'}}, {'attributes':{'Anyag':'Pamut'}}]:
            with self.assertRaises(ValueError):
                validate_webshop_product({'name':'Póló'}, [variant | changes], attributes)
        with self.assertRaises(ValueError):
            validate_webshop_product({'name':'Póló'}, [variant, variant | {'sku':'polo-m'}], attributes)

    def test_basket_validation(self):
        item = dict(variant_id=str(uuid4()), quantity=1)
        validate_webshop_items([item])
        for items in [[], [item,item], [item | {'quantity':100}], [item | {'quantity':1.5}]]:
            with self.assertRaises(ValueError):
                validate_webshop_items(items)

    def endpoints(self, role, db):
        tree = ast.parse((Path(__file__).resolve().parents[1]/'pwa_api.py').read_text(encoding='utf8'))
        names = {'require_webshop_admin','webshop_products','webshop_requests','create_webshop_request','manage_webshop_request','save_webshop_product','save_webshop_attribute'}
        nodes = [n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
        for node in nodes:
            node.decorator_list=[]
        ns = dict(Any=Any, UUID=UUID, HTTPException=ApiError, Query=lambda **k:k.get('default'),Cookie=lambda **k:None,
                  WebshopOrderRequest=Any,WebshopOrderActionRequest=Any,WebshopProductRequest=Any,WebshopAttributeRequest=Any,
                  require_user=lambda _:dict(role=role,username='Futár'),courier_identity=lambda _:('6498','Futár'),
                  supabase_rest=db,validate_webshop_items=validate_webshop_items,validate_webshop_product=validate_webshop_product,quote=str)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'webshop_endpoints','exec'),ns)
        return ns

    def test_non_admin_cannot_manage_or_read_admin_orders(self):
        ns=self.endpoints('coordinator',lambda *a,**k:self.fail('Unauthorized DB access'))
        with self.assertRaises(ApiError) as error:
            ns['webshop_requests'](admin=True)
        self.assertEqual(error.exception.status_code,403)
        with self.assertRaises(ApiError):
            ns['save_webshop_product'](None)
        with self.assertRaises(ApiError):
            ns['manage_webshop_request'](uuid4(),SimpleNamespace(status='fulfilled',response=''))

    def test_own_orders_scoped_and_request_uses_session_owner(self):
        calls=[]
        def db(*args,**kwargs):
            calls.append((args,kwargs))
            return [] if args[0]=='GET' else str(uuid4())
        ns=self.endpoints('courier',db)
        ns['webshop_requests']()
        self.assertEqual(calls[0][1]['params']['courier_id'],'eq.6498')
        item=dict(variant_id=str(uuid4()),quantity=2,expected_price_huf=4500)
        payload=SimpleNamespace(request_key=uuid4(),note=' BUD2 ',items=[SimpleNamespace(model_dump=lambda **k:item)])
        self.assertTrue(ns['create_webshop_request'](payload)['ok'])
        self.assertEqual(calls[-1][1]['payload']['p_courier'],'6498')
        self.assertEqual(calls[-1][1]['payload']['p_items'][0]['expected_price_huf'],4500)


if __name__=='__main__':
    unittest.main()
