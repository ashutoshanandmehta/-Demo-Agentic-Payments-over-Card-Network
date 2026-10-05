"""Run simulated Blinkit MCP actions as focused commands."""
from common import *

SCHEMA={'type':'object','properties':{'query':{'type':'string'},'quantity':{'type':'integer','minimum':1},
 'currency':{'type':'string','enum':['INR']},'postal_code':{'type':'string'},
 'price_upto_minor':{'type':'integer','minimum':0}},
 'required':['query','quantity','currency','postal_code'],'additionalProperties':False}
TOOLS=[{'name':'search_products','description':'Search the demo grocery catalog','inputSchema':SCHEMA},
 {'name':'create_cart','description':'Build a cart','inputSchema':{'type':'object','properties':{'product_id':{'type':'string'},'quantity':{'type':'integer','minimum':1}},'required':['product_id','quantity']}},
 {'name':'create_checkout','description':'Lock cart terms','inputSchema':{'type':'object','properties':{'cart_id':{'type':'string'}},'required':['cart_id']}},
 {'name':'complete_checkout','description':'Send the agent order and SPT to Blinkit','inputSchema':{'type':'object','properties':{'cart_id':{'type':'string'},'order_id':{'type':'string'},'SPT':{'type':'string'}},'required':['cart_id','order_id','SPT']}}]


def work(s,args):
    action=args.action
    if action=='establish_connection':
        s['mcp_session']={'session_id':'mcp-session-01','merchant_id':'blinkit','connected':True}
        s['merchant_account']={'merchant_account_id':'merchant_blinkit_01','merchant_id':'blinkit','network_merchant_id':'mid_blinkit_demo','stripe_profile_id':'profile_blinkit_demo','bank_reference':'bank_blinkit_demo','api_key':'demo_blinkit_key','status':'active'}
        req={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'demo-v1','capabilities':{},'clientInfo':{'name':'shopping-agent','version':'1.0'}}}
        out={'response':{'jsonrpc':'2.0','id':1,'result':{'protocolVersion':'demo-v1','capabilities':{'tools':{}},'serverInfo':{'name':'Blinkit Demo Commerce MCP','version':'1.0'}}},'notification':{'jsonrpc':'2.0','method':'notifications/initialized'},'session':s['mcp_session']}
        return req,['Simulated local MCP initialization.'],out,True
    if action=='list_tools':
        s['tools']=TOOLS
        return ({'method':'tools/list','params':{}},['Return simulated tool names and schemas.'],{'tools':TOOLS},True)
    if action=='read_schema':
        selected=next(t for t in s['tools'] if t['name']=='search_products')
        s['selected_tool']=selected
        return ({'selected_tool':'search_products'},['Use schema already returned by list_tools.'],selected,True)
    if action=='search_product':
        query=pick(args,'query','Product name','banana')
        quantity=pick(args,'quantity','Quantity',12,int)
        postal=pick(args,'postal_code','Delivery postal code',s['intent']['postal_code'])
        require(quantity>0,'Quantity must be positive.')
        require(postal==s['intent']['postal_code'],'LOCATION_NOT_AUTHORIZED: use the postal code in the user permission.')
        price_upto=money(pick(args,'price_upto','Price filter up to (INR)','300'))
        require('banana' in query.lower(),'DEMO_NO_RESULTS: only banana is in this catalog.')
        price=1375
        require(price<=price_upto,'DEMO_NO_RESULTS: no product is within the requested price filter.')
        offer={'merchant_id':'blinkit','product_id':'4','product':'banana','name':'Fresh banana','unit':'piece','requested_quantity':quantity,'unit_price_minor':price,'stock':100,'delivery_fee_minor':1000,'handling_fee_minor':1000,'currency':'INR','category':'grocery','estimated_total_minor':price*quantity+2000,'delivery_minutes':11}
        s['offer']=offer
        return ({'method':'tools/call','name':'search_products','arguments':{'query':query,'quantity':quantity,'currency':'INR','postal_code':postal,'price_upto_minor':price_upto}},['Filter catalog offers by maximum unit price.'],{'merchant_id':'blinkit','products':[offer]},True)
    if action=='create_cart':
        o=s['offer']; product_id=pick(args,'product_id','Product ID',o['product_id'])
        require(product_id==o['product_id'],'UNKNOWN_PRODUCT_ID: use the product ID returned by search.')
        quantity=pick(args,'quantity','Cart quantity (pieces)',o['requested_quantity'],int)
        require(0<quantity<=o['stock'],'OUT_OF_STOCK_OR_INVALID_QUANTITY')
        c={'cart_id':'cart-101','merchant_id':'blinkit','items':[{'product_id':product_id,'product':'banana','quantity':quantity,'unit':'piece','unit_price_minor':o['unit_price_minor']}],'category':o['category'],'currency':'INR','item_amount_minor':quantity*o['unit_price_minor'],'delivery_fee_minor':o['delivery_fee_minor'],'handling_fee_minor':o['handling_fee_minor'],'amount_minor':quantity*o['unit_price_minor']+o['delivery_fee_minor']+o['handling_fee_minor'],'address':s['intent']['address'],'postal_code':s['intent']['postal_code']}
        s['cart']=c
        return ({'product_id':product_id,'quantity':quantity,'address':c['address'],'postal_code':c['postal_code']},['Recheck stock and calculate the cart total.'],c,True)
    c=s['cart']; minutes=pick(args,'expires_in_minutes','Checkout lifetime (minutes)',120,int)
    require(minutes>0,'Checkout lifetime must be positive.')
    body={k:v for k,v in c.items() if k!='cart_id'}
    body.update({'checkout_id':'checkout-101','order_id':'order-101','expires_at':expiry(minutes)})
    body['checkout_hash']=digest(body); s['checkout']=sign(body,s['merchant_signing_key'])
    return ({'cart_id':c['cart_id'],'expires_in_minutes':minutes},['Lock and sign the checkout terms.'],s['checkout'],True)


def main():
    p=parser(__doc__); g=p.add_mutually_exclusive_group(required=False)
    names=['establish_connection','list_tools','search_product','create_cart','create_checkout']
    for name in names:g.add_argument('--'+name,action='store_true')
    p.add_argument('--query');p.add_argument('--quantity',type=int);p.add_argument('--postal_code');p.add_argument('--price_upto','--price-upto',dest='price_upto');p.add_argument('--product_id');p.add_argument('--expires_in_minutes',type=int)
    p.add_argument('--cart_id');p.add_argument('--order_id');p.add_argument('--STP','--SPT',dest='spt')
    args=p.parse_args()
    selected=[n for n in names if getattr(args,n)]
    if not selected and args.cart_id and args.order_id and args.spt:
        return send_order_to_merchant(args)
    if len(selected)!=1:
        p.error('Choose an MCP action or provide --cart_id, --order_id, and --STP.')
    if args.cart_id or args.order_id or args.spt:
        p.error('Send --cart_id, --order_id, and --STP together as a separate command.')
    args.action=selected[0]
    step={'establish_connection':5,'list_tools':6,'search_product':8,'create_cart':9,'create_checkout':10}[args.action]
    title={'establish_connection':'Initialize Blinkit MCP connection','list_tools':'List Blinkit tools','search_product':'Search Blinkit products','create_cart':'Create Blinkit cart','create_checkout':'Create and sign Blinkit checkout'}[args.action]
    if args.action=='search_product':
        args.action='read_schema';execute(7,'Select search tool schema',work,args,quiet=True);args.action='search_product'
    execute(step,title,work,args,show_next_step=False)


def send_order_to_merchant(args):
    folder=Path(args.state_dir).resolve()
    try:
        with locked(folder):
            state=json.loads((folder/'state.json').read_text(encoding='utf-8'))
            live_permission(state)
            c=trusted_checkout(state);cart=state['cart'];token=state['scoped_token']
            require(args.cart_id==cart['cart_id'],'CART_NOT_FOUND')
            require(args.order_id==c['order_id'],'ORDER_ID_MISMATCH')
            require(args.spt==token['token_id'],'SPT_NOT_FOUND')
            require(not token['revoked'],'TOKEN_REVOKED')
            require(valid_until(token['expires_at']),'TOKEN_EXPIRED')
            require(token['status']=='issued','TOKEN_ALREADY_REDEEMED')
            payload={'STP':args.spt,'checkout_id':c['checkout_id'],'order_id':c['order_id'],'amount_minor':c['amount_minor'],'currency':c['currency'],'checkout_hash':c['checkout_hash'],'idempotency_key':c['order_id']+'-payment-1'}
            previous=state.get('merchant_order_submission')
            require(previous is None or previous==payload,'ORDER_SUBMISSION_MISMATCH')
            if previous is None:
                state['merchant_order_submission']=payload
                state['events'].append({'event':'blinkit.order_submitted','agent_id':token['agent_id'],
                                        'order_id':c['order_id'],'at':stamp()})
                atomic_json(folder/'state.json',state)
            print('AGENT → BLINKIT MCP REQUEST')
            print(json.dumps({'cart_id':cart['cart_id'],'order_id':c['order_id'],'STP':args.spt},indent=2))
            print('\nBLINKIT PAYMENT REQUEST DETAILS')
            print(json.dumps(payload,indent=2))
    except (DemoError,ValueError,KeyError,OSError) as e:
        print('\nBLOCKED: '+str(e),file=sys.stderr);raise SystemExit(2)

if __name__=='__main__':main()
