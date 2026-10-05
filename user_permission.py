"""Create a per-agent merchant, category, spending, and delivery permission."""
from common import *


def normalize_agent_id(value):
    value=str(value).strip()
    require(bool(value),'Agent ID is required.')
    return 'shopping-agent-'+value if value.isdigit() else value


def work(s,args):
    per_tx=money(pick(args,'transaction_limit','Per-transaction limit (INR)','500'))
    monthly=money(pick(args,'monthly_limit','Monthly spending limit (INR)','3000'))
    minutes=pick(args,'expires_in_minutes','Permission lifetime (minutes)',43200,int)
    agent=normalize_agent_id(pick(args,'agent_id','Agent ID','12'))
    category=pick(args,'category','Category','grocery').strip().lower()
    require(bool(category),'Category is required.')
    address=pick(args,'address','Delivery address','Hall 12, IIT Kanpur')
    postal=pick(args,'postal_code','Postal code','208016')
    require(postal.isdigit() and len(postal)==6,'Use a 6-digit postal code.')
    merchant=pick(args,'merchant','Allowed merchant','blinkit').strip().lower()
    intent={'agent_id':agent,'merchant_id':merchant,'category':category,'currency':'INR','address':address,'postal_code':postal}
    permission={'permission_id':'permission-'+agent.split('-')[-1],'user_id':'user-77','agent_id':agent,'allowed_merchants':[merchant],'category':category,'currency':'INR','address':address,'postal_code':postal,'transaction_limit_minor':per_tx,'monthly_limit_minor':monthly,'expires_at':expiry(minutes),'revoked':args.revoked}
    s['intent']=intent;s['permission']=sign(permission,s['user_signing_key'])
    month=(now()+timedelta(hours=5,minutes=30)).strftime('%Y-%m')
    s['budget']={'month':month,'captured_minor':0,'reserved_minor':0,'monthly_limit_minor':monthly}
    s.setdefault('agent_permissions',{})[agent]={'permission_id':permission['permission_id'],'category':category,'allowed_merchants':[merchant],'transaction_limit_minor':per_tx,'monthly_limit_minor':monthly,'address':address,'postal_code':postal,'created_at':stamp()}
    return ({'payment_method_id':s['vault']['payment_method_id'],'agent_id':agent,'merchant':merchant,'category':category,'transaction_limit':show_money(per_tx),'monthly_limit':show_money(monthly),'delivery_address':address,'postal_code':postal,'permission_lifetime_minutes':minutes},['Create and sign category-based permission. Monthly spend starts at INR 0.00 and is tracked at capture.'],{'permission':s['permission'],'monthly_budget':s['budget']},True)


if __name__=='__main__':
    p=parser(__doc__);p.add_argument('--transaction-limit');p.add_argument('--monthly-limit');p.add_argument('--expires-in-minutes',type=int);p.add_argument('--agent-id');p.add_argument('--category');p.add_argument('--address');p.add_argument('--postal-code');p.add_argument('--merchant');p.add_argument('--revoked',action='store_true')
    execute(4,'Create user permission',work,p.parse_args(),show_next_step=False)
