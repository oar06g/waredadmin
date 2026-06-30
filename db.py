"""
shared/db.py — Supabase Client
يستبدل SQLAlchemy بالكامل
"""
import os, hashlib
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_url: str = os.environ.get("SUPABASE_URL", "")
_key: str = os.environ.get("SUPABASE_KEY", "")
if not _url or not _key:
    raise EnvironmentError("SUPABASE_URL و SUPABASE_KEY مطلوبان في .env")

supabase: Client = create_client(_url, _key)

TRANSACTION_ICONS = {
    'ad_reward':           '📺',
    'referral_commission': '👥',
    'withdrawal_request':  '💸',
    'withdrawal_approved': '✅',
    'withdrawal_rejected': '❌',
    'admin_action':        '⚙️',
    'task_reward':         '✅',
}

def hash_password(p): return hashlib.sha256(p.encode()).hexdigest()
def check_password(p, h): return hash_password(p) == h

def fmt_date(s):
    if not s: return ''
    try:
        return datetime.fromisoformat(s.replace('Z','+00:00')).strftime('%Y-%m-%d %H:%M')
    except: return s[:16]

# ── USERS ─────────────────────────────────────────────────────────────────────
def get_user(user_id):
    try:
        r = supabase.table('users').select('*').eq('user_id', user_id).single().execute()
        return r.data
    except: return None

def get_user_by_username(username):
    try:
        r = supabase.table('users').select('*').eq('username', username).single().execute()
        return r.data
    except: return None

def create_user(user_id, username, first_name='', email='', password='', referrer_id=None):
    data = {
        'user_id': user_id, 'username': username, 'first_name': first_name,
        'email': email, 'password_hash': hash_password(password) if password else 'tg_no_password',
        'referrer_id': referrer_id, 'balance': 0, 'total_earned': 0,
        'referral_count': 0, 'ads_today': 0, 'ads_since_captcha': 0,
        'last_ad_date': '', 'join_date': datetime.utcnow().isoformat(),
    }
    r = supabase.table('users').insert(data).execute()
    if referrer_id:
        inc_referral_count(referrer_id)
    return r.data[0] if r.data else data

def update_user(user_id, **kwargs):
    r = supabase.table('users').update(kwargs).eq('user_id', user_id).execute()
    return r.data[0] if r.data else None

def inc_referral_count(referrer_id):
    u = get_user(referrer_id)
    if u:
        supabase.table('users').update({'referral_count': (u.get('referral_count') or 0) + 1}).eq('user_id', referrer_id).execute()

def delete_user(user_id):
    supabase.table('users').delete().eq('user_id', user_id).execute()

def get_all_users(search='', page=1, per_page=20):
    q = supabase.table('users').select('*', count='exact')
    if search:
        q = q.or_(f"user_id.ilike.%{search}%,username.ilike.%{search}%,first_name.ilike.%{search}%")
    q = q.order('join_date', desc=True)
    offset = (page-1)*per_page
    r = q.range(offset, offset+per_page-1).execute()
    total = r.count or 0
    return r.data or [], total, max(1,(total+per_page-1)//per_page)

def user_to_dict(u):
    return {
        'user_id':        u.get('user_id',''),
        'username':       u.get('username',''),
        'first_name':     u.get('first_name') or u.get('username',''),
        'balance':        float(u.get('balance') or 0),
        'total_earned':   float(u.get('total_earned') or 0),
        'referrer_id':    u.get('referrer_id'),
        'referral_count': int(u.get('referral_count') or 0),
        'ads_today':      int(u.get('ads_today') or 0),
        'ads_since_captcha': int(u.get('ads_since_captcha') or 0),
        'last_ad_time':   u.get('last_ad_time'),
        'join_date':      fmt_date(u.get('join_date','')),
    }

def increment_ads_since_captcha(user_id):
    u = get_user(user_id)
    if not u: return 0
    new = (u.get('ads_since_captcha') or 0) + 1
    update_user(user_id, ads_since_captcha=new)
    return new

def reset_captcha_count(user_id):
    update_user(user_id, ads_since_captcha=0)

# ── WITHDRAWALS ───────────────────────────────────────────────────────────────
def create_withdrawal(user_id, amount, commission, wallet_type, wallet_number):
    data = {
        'user_id': user_id, 'amount': amount, 'commission': commission,
        'wallet_type': wallet_type, 'wallet_number': wallet_number,
        'status': 'pending', 'created_at': datetime.utcnow().isoformat(),
    }
    r = supabase.table('withdrawals').insert(data).execute()
    return r.data[0] if r.data else data

def get_user_withdrawals(user_id, limit=20):
    r = supabase.table('withdrawals').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(limit).execute()
    return r.data or []

def get_all_withdrawals(status='all', limit=100):
    q = supabase.table('withdrawals').select('*')
    if status != 'all': q = q.eq('status', status)
    r = q.order('created_at', desc=True).limit(limit).execute()
    rows = r.data or []
    for w in rows:
        u = get_user(w.get('user_id',''))
        w['username'] = u.get('username', w.get('user_id','')) if u else w.get('user_id','')
    return rows

def get_withdrawal(wid):
    try:
        r = supabase.table('withdrawals').select('*').eq('id', wid).single().execute()
        return r.data
    except: return None

def update_withdrawal_status(wid, status):
    supabase.table('withdrawals').update({'status': status}).eq('id', wid).execute()

def withdrawal_to_dict(w):
    return {
        'id':            w.get('id'),
        'user_id':       w.get('user_id',''),
        'username':      w.get('username',''),
        'amount':        float(w.get('amount') or 0),
        'commission':    float(w.get('commission') or 0),
        'wallet_type':   w.get('wallet_type',''),
        'wallet_number': w.get('wallet_number',''),
        'status':        w.get('status','pending'),
        'date':          fmt_date(w.get('created_at','')),
    }

# ── TRANSACTIONS ──────────────────────────────────────────────────────────────
def create_transaction(user_id, type_, amount, description=''):
    supabase.table('transactions').insert({
        'user_id': user_id, 'type': type_, 'amount': amount,
        'description': description, 'created_at': datetime.utcnow().isoformat(),
    }).execute()

def get_user_transactions(user_id, limit=30):
    r = supabase.table('transactions').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(limit).execute()
    return r.data or []

def transaction_to_dict(t):
    return {
        'id':          t.get('id'),
        'type':        t.get('type',''),
        'icon':        TRANSACTION_ICONS.get(t.get('type',''),'💰'),
        'amount':      float(t.get('amount') or 0),
        'description': t.get('description',''),
        'date':        fmt_date(t.get('created_at','')),
    }

# ── SETTINGS ──────────────────────────────────────────────────────────────────
def get_settings():
    try:
        r = supabase.table('settings').select('*').limit(1).execute()
        if r.data:
            s = r.data[0]
            return {
                'reward_per_ad':         float(s.get('reward_per_ad')         or 0.5),
                'min_withdraw':          float(s.get('minimum_withdraw')       or 5),
                'cooldown_seconds':      int(s.get('cooldown_seconds')         or 20),
                'max_ads_per_day':       int(s.get('max_ads_per_day')          or 100),
                'withdrawal_commission': float(s.get('withdrawal_commission')  or 1),
                'captcha_every':         int(s.get('captcha_every')            or 10),
                'welcome_message':       s.get('welcome_message',''),
                'welcome_active':        bool(s.get('welcome_active', False)),
                'active_theme':          s.get('active_theme','dark_gold'),
                'min_vodafone':  float(s.get('min_vodafone')  or 5),
                'fee_vodafone':  float(s.get('fee_vodafone')  or 1),
                'min_etisalat':  float(s.get('min_etisalat')  or 5),
                'fee_etisalat':  float(s.get('fee_etisalat')  or 1),
                'min_orange':    float(s.get('min_orange')    or 5),
                'fee_orange':    float(s.get('fee_orange')    or 1),
                'min_we':        float(s.get('min_we')        or 5),
                'fee_we':        float(s.get('fee_we')        or 1),
                'min_binance':   float(s.get('min_binance')   or 10),
                'fee_binance':   float(s.get('fee_binance')   or 0.5),
                'min_ethereum':  float(s.get('min_ethereum')  or 20),
                'fee_ethereum':  float(s.get('fee_ethereum')  or 2),
                'min_usdt':          float(s.get('min_usdt')          or 10),
                'fee_usdt':          float(s.get('fee_usdt')          or 1),
                'usdt_networks':     s.get('usdt_networks',    'TRC20,ERC20,BEP20'),
                'active_usdt_nets':  s.get('active_usdt_nets', 'TRC20,ERC20,BEP20'),
            }
    except: pass
    default = {
        'reward_per_ad':0.5,'minimum_withdraw':5,'cooldown_seconds':20,
        'max_ads_per_day':100,'withdrawal_commission':1,'captcha_every':10,
        'welcome_message':'','welcome_active':False,'active_theme':'dark_gold',
        'min_vodafone':5,'fee_vodafone':1,'min_etisalat':5,'fee_etisalat':1,
        'min_orange':5,'fee_orange':1,'min_we':5,'fee_we':1,
        'min_binance':10,'fee_binance':0.5,'min_ethereum':20,'fee_ethereum':2,
        'min_usdt':10,'fee_usdt':1,'usdt_networks':'TRC20,ERC20,BEP20','active_usdt_nets':'TRC20,ERC20,BEP20',
    }
    supabase.table('settings').insert(default).execute()
    default['min_withdraw'] = default.pop('minimum_withdraw')
    return default

def update_settings(**kwargs):
    if 'min_withdraw' in kwargs:
        kwargs['minimum_withdraw'] = kwargs.pop('min_withdraw')
    allowed = {
        'reward_per_ad','minimum_withdraw','cooldown_seconds','max_ads_per_day',
        'withdrawal_commission','captcha_every','welcome_message','welcome_active','active_theme',
        'min_vodafone','fee_vodafone','min_etisalat','fee_etisalat',
        'min_orange','fee_orange','min_we','fee_we',
        'min_binance','fee_binance','min_ethereum','fee_ethereum',
        'min_usdt','fee_usdt','usdt_networks','active_usdt_nets',
    }
    kwargs = {k:v for k,v in kwargs.items() if k in allowed}
    try:
        r = supabase.table('settings').select('id').limit(1).execute()
        if r.data:
            supabase.table('settings').update(kwargs).eq('id', r.data[0]['id']).execute()
    except: pass
    return get_settings()

# ── FEATURED BOTS ─────────────────────────────────────────────────────────────
def get_active_bots():
    r = supabase.table('featured_bots').select('*').eq('is_active',True).order('id',desc=True).execute()
    return r.data or []

def get_all_bots():
    r = supabase.table('featured_bots').select('*').order('id',desc=True).execute()
    return r.data or []

def create_bot(title, message, bot_link):
    r = supabase.table('featured_bots').insert({'title':title,'message':message,'bot_link':bot_link,'is_active':True}).execute()
    return r.data[0] if r.data else {}

def update_bot(bot_id, **kwargs):
    r = supabase.table('featured_bots').update(kwargs).eq('id',bot_id).execute()
    return r.data[0] if r.data else None

def delete_bot(bot_id):
    supabase.table('featured_bots').delete().eq('id',bot_id).execute()

def bot_to_dict(b):
    return {
        'id':b.get('id'),'title':b.get('title',''),'message':b.get('message',''),
        'bot_link':b.get('bot_link',''),'is_active':b.get('is_active',True),
        'created_at':fmt_date(b.get('created_at',''))
    }

# ── TASKS ─────────────────────────────────────────────────────────────────────
def get_active_tasks(user_id=None):
    r = supabase.table('tasks').select('*').eq('is_active',True).order('id',desc=True).execute()
    tasks = r.data or []
    if user_id:
        # استثني المهام اللي المستخدم ده خلّصها
        done = get_user_done_tasks(user_id)
        done_ids = {d['task_id'] for d in done}
        tasks = [t for t in tasks if t['id'] not in done_ids]
    return tasks

def get_all_tasks():
    r = supabase.table('tasks').select('*').order('id',desc=True).execute()
    return r.data or []

def create_task(title, description, link, reward, task_type='visit'):
    data = {
        'title':title,'description':description,'link':link,
        'reward':reward,'task_type':task_type,'is_active':True,
        'created_at':datetime.utcnow().isoformat(),
    }
    r = supabase.table('tasks').insert(data).execute()
    return r.data[0] if r.data else data

def update_task(task_id, **kwargs):
    r = supabase.table('tasks').update(kwargs).eq('id',task_id).execute()
    return r.data[0] if r.data else None

def delete_task(task_id):
    supabase.table('tasks').delete().eq('id',task_id).execute()

def get_user_done_tasks(user_id):
    r = supabase.table('user_tasks').select('*').eq('user_id',user_id).execute()
    return r.data or []

def complete_task(user_id, task_id):
    """تسجيل إتمام المهمة وإضافة المكافأة"""
    # تحقق إن المهمة موجودة ومش متعملتش قبل كده
    try:
        r = supabase.table('user_tasks').select('id').eq('user_id',user_id).eq('task_id',task_id).single().execute()
        if r.data:
            return None, 'قمت بهذه المهمة من قبل'
    except: pass

    # جيب بيانات المهمة
    try:
        t = supabase.table('tasks').select('*').eq('id',task_id).eq('is_active',True).single().execute()
        if not t.data:
            return None, 'المهمة غير موجودة أو منتهية'
        task = t.data
    except:
        return None, 'المهمة غير موجودة'

    reward = float(task.get('reward') or 0)

    # إضافة المكافأة
    user = get_user(user_id)
    if not user:
        return None, 'مستخدم غير موجود'

    new_bal   = round(float(user.get('balance') or 0) + reward, 10)
    new_earn  = round(float(user.get('total_earned') or 0) + reward, 10)
    update_user(user_id, balance=new_bal, total_earned=new_earn)

    # تسجيل الإتمام للمستخدم ده بس
    supabase.table('user_tasks').insert({
        'user_id':user_id,'task_id':task_id,
        'reward':reward,'completed_at':datetime.utcnow().isoformat()
    }).execute()

    # تسجيل العملية
    create_transaction(user_id,'task_reward',reward,f'مكافأة مهمة: {task.get("title","")}')

    return reward, None

def task_to_dict(t):
    return {
        'id':t.get('id'),'title':t.get('title',''),
        'description':t.get('description',''),'link':t.get('link',''),
        'reward':float(t.get('reward') or 0),'task_type':t.get('task_type','visit'),
        'is_active':t.get('is_active',True),'created_at':fmt_date(t.get('created_at',''))
    }

# ── ADMIN STATS ───────────────────────────────────────────────────────────────
def get_admin_stats():
    today = datetime.utcnow().strftime('%Y-%m-%d')
    total_users   = supabase.table('users').select('id',count='exact').execute().count or 0
    bal_r         = supabase.table('users').select('balance').execute()
    total_balance = sum(float(u.get('balance') or 0) for u in (bal_r.data or []))
    ear_r         = supabase.table('users').select('total_earned').execute()
    total_earned  = sum(float(u.get('total_earned') or 0) for u in (ear_r.data or []))
    pending  = supabase.table('withdrawals').select('id',count='exact').eq('status','pending').execute().count or 0
    total_w  = supabase.table('withdrawals').select('id',count='exact').execute().count or 0
    new_today= supabase.table('users').select('id',count='exact').gte('join_date',today+'T00:00:00').execute().count or 0
    sett = get_settings()
    return {
        'total_users':total_users,'total_balance':round(total_balance,5),
        'total_earned':round(total_earned,5),'pending_withdrawals':pending,
        'total_withdrawals':total_w,'new_today':new_today,**sett
    }

def get_top_referrers(limit=50):
    r = supabase.table('users').select('user_id,username,referral_count,total_earned').gt('referral_count',0).order('referral_count',desc=True).limit(limit).execute()
    return r.data or []
