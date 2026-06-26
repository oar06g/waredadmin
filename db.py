"""
shared/db.py — Supabase Client
يستبدل SQLAlchemy بالكامل
جميع عمليات CRUD تمر من هنا
"""
import os, hashlib
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# ── إنشاء الـ Client ───────────────────────────────────────────────────────
_url: str    = os.environ.get("SUPABASE_URL", "")
_key: str    = os.environ.get("SUPABASE_KEY", "")

if not _url or not _key:
    raise EnvironmentError("SUPABASE_URL و SUPABASE_KEY مطلوبان في ملف .env")

supabase: Client = create_client(_url, _key)

# ══════════════════════════════════════════════════════════════════════════════
# أدوات مساعدة
# ══════════════════════════════════════════════════════════════════════════════

TRANSACTION_ICONS = {
    'ad_reward':           '📺',
    'referral_commission': '👥',
    'withdrawal_request':  '💸',
    'withdrawal_approved': '✅',
    'withdrawal_rejected': '❌',
    'admin_action':        '⚙️',
}

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def check_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

def fmt_date(dt_str: str) -> str:
    """تحويل ISO timestamp إلى yyyy-mm-dd HH:MM"""
    if not dt_str:
        return ''
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M')
    except Exception:
        return dt_str[:16] if dt_str else ''

# ══════════════════════════════════════════════════════════════════════════════
# USERS
# ══════════════════════════════════════════════════════════════════════════════

def get_user(user_id: str) -> dict | None:
    r = supabase.table('users').select('*').eq('user_id', user_id).single().execute()
    return r.data if r.data else None

def get_user_by_username(username: str) -> dict | None:
    r = supabase.table('users').select('*').eq('username', username).single().execute()
    return r.data if r.data else None

def create_user(user_id: str, username: str, first_name: str = '',
                email: str = '', password: str = '',
                referrer_id: str | None = None) -> dict:
    data = {
        'user_id':       user_id,
        'username':      username,
        'first_name':    first_name,
        'email':         email,
        'password_hash': hash_password(password) if password else 'tg_no_password',
        'referrer_id':   referrer_id,
        'balance':       0,
        'total_earned':  0,
        'referral_count':0,
        'ads_today':     0,
        'last_ad_date':  '',
        'join_date':     datetime.utcnow().isoformat(),
    }
    r = supabase.table('users').insert(data).execute()
    # زيادة عداد الإحالات للمحيل
    if referrer_id:
        inc_referral_count(referrer_id)
    return r.data[0] if r.data else data

def update_user(user_id: str, **kwargs) -> dict | None:
    r = supabase.table('users').update(kwargs).eq('user_id', user_id).execute()
    return r.data[0] if r.data else None

def inc_referral_count(referrer_id: str):
    user = get_user(referrer_id)
    if user:
        supabase.table('users').update({
            'referral_count': (user.get('referral_count') or 0) + 1
        }).eq('user_id', referrer_id).execute()

def add_balance(user_id: str, amount: float) -> float:
    user = get_user(user_id)
    if not user:
        return 0
    new_bal = float(user.get('balance') or 0) + amount
    update_user(user_id, balance=new_bal)
    return new_bal

def user_to_dict(u: dict) -> dict:
    return {
        'user_id':        u.get('user_id', ''),
        'username':       u.get('username', ''),
        'first_name':     u.get('first_name') or u.get('username', ''),
        'balance':        float(u.get('balance') or 0),
        'total_earned':   float(u.get('total_earned') or 0),
        'referrer_id':    u.get('referrer_id'),
        'referral_count': int(u.get('referral_count') or 0),
        'ads_today':      int(u.get('ads_today') or 0),
        'last_ad_time':   u.get('last_ad_time'),
        'join_date':      fmt_date(u.get('join_date', '')),
    }

def get_all_users(search: str = '', page: int = 1, per_page: int = 20):
    q = supabase.table('users').select('*', count='exact')
    if search:
        q = q.or_(f"user_id.ilike.%{search}%,username.ilike.%{search}%,first_name.ilike.%{search}%")
    q = q.order('join_date', desc=True)
    offset = (page - 1) * per_page
    q = q.range(offset, offset + per_page - 1)
    r = q.execute()
    total = r.count or 0
    pages = max(1, (total + per_page - 1) // per_page)
    return r.data or [], total, pages

def delete_user(user_id: str):
    supabase.table('users').delete().eq('user_id', user_id).execute()

# ══════════════════════════════════════════════════════════════════════════════
# WITHDRAWALS
# ══════════════════════════════════════════════════════════════════════════════

def create_withdrawal(user_id: str, amount: float, commission: float,
                      wallet_type: str, wallet_number: str) -> dict:
    data = {
        'user_id':       user_id,
        'amount':        amount,
        'commission':    commission,
        'wallet_type':   wallet_type,
        'wallet_number': wallet_number,
        'status':        'pending',
        'created_at':    datetime.utcnow().isoformat(),
    }
    r = supabase.table('withdrawals').insert(data).execute()
    return r.data[0] if r.data else data

def get_user_withdrawals(user_id: str, limit: int = 20) -> list:
    r = supabase.table('withdrawals').select('*')\
        .eq('user_id', user_id)\
        .order('created_at', desc=True)\
        .limit(limit).execute()
    return r.data or []

def get_all_withdrawals(status: str = 'all', limit: int = 100) -> list:
    q = supabase.table('withdrawals').select('*')
    if status != 'all':
        q = q.eq('status', status)
    r = q.order('created_at', desc=True).limit(limit).execute()
    rows = r.data or []
    # نجيب اسم المستخدم لكل طلب
    for w in rows:
        u = get_user(w.get('user_id', ''))
        w['username'] = u.get('username', w.get('user_id', '')) if u else w.get('user_id', '')
    return rows

def update_withdrawal_status(withdrawal_id: int, status: str):
    supabase.table('withdrawals').update({'status': status})\
        .eq('id', withdrawal_id).execute()

def get_withdrawal(withdrawal_id: int) -> dict | None:
    r = supabase.table('withdrawals').select('*').eq('id', withdrawal_id).single().execute()
    return r.data if r.data else None

def withdrawal_to_dict(w: dict) -> dict:
    return {
        'id':            w.get('id'),
        'user_id':       w.get('user_id', ''),
        'username':      w.get('username', ''),
        'amount':        float(w.get('amount') or 0),
        'commission':    float(w.get('commission') or 0),
        'wallet_type':   w.get('wallet_type', ''),
        'wallet_number': w.get('wallet_number', ''),
        'status':        w.get('status', 'pending'),
        'date':          fmt_date(w.get('created_at', '')),
    }

# ══════════════════════════════════════════════════════════════════════════════
# TRANSACTIONS
# ══════════════════════════════════════════════════════════════════════════════

def create_transaction(user_id: str, type_: str, amount: float, description: str = ''):
    data = {
        'user_id':     user_id,
        'type':        type_,
        'amount':      amount,
        'description': description,
        'created_at':  datetime.utcnow().isoformat(),
    }
    supabase.table('transactions').insert(data).execute()

def get_user_transactions(user_id: str, limit: int = 30) -> list:
    r = supabase.table('transactions').select('*')\
        .eq('user_id', user_id)\
        .order('created_at', desc=True)\
        .limit(limit).execute()
    return r.data or []

def transaction_to_dict(t: dict) -> dict:
    return {
        'id':          t.get('id'),
        'type':        t.get('type', ''),
        'icon':        TRANSACTION_ICONS.get(t.get('type', ''), '💰'),
        'amount':      float(t.get('amount') or 0),
        'description': t.get('description', ''),
        'date':        fmt_date(t.get('created_at', '')),
    }

# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

_settings_cache: dict = {}

def get_settings() -> dict:
    r = supabase.table('settings').select('*').limit(1).execute()
    if r.data:
        s = r.data[0]
        return {
            # إعدادات الإعلانات
            'reward_per_ad':         float(s.get('reward_per_ad')         or 0.5),
            'min_withdraw':          float(s.get('minimum_withdraw')       or 5),
            'cooldown_seconds':      int(s.get('cooldown_seconds')         or 20),
            'max_ads_per_day':       int(s.get('max_ads_per_day')          or 100),
            'withdrawal_commission': float(s.get('withdrawal_commission')  or 1),
            # التحقق البشري
            'captcha_every':         int(s.get('captcha_every')            or 10),
            # رسالة الترحيب
            'welcome_message':       s.get('welcome_message', ''),
            'welcome_active':        bool(s.get('welcome_active', False)),
            # الثيم
            'active_theme':          s.get('active_theme', 'dark_gold'),
            # حدود ورسوم كل طريقة سحب
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
            # USDT
            'min_usdt':          float(s.get('min_usdt')          or 10),
            'fee_usdt':          float(s.get('fee_usdt')          or 1),
            'usdt_networks':     s.get('usdt_networks',     'TRC20,ERC20,BEP20'),
            'active_usdt_nets':  s.get('active_usdt_nets',  'TRC20,ERC20,BEP20'),
            'fee_ethereum':  float(s.get('fee_ethereum')  or 2),
        }
    default = {
        'reward_per_ad': 0.5, 'minimum_withdraw': 5.0,
        'cooldown_seconds': 20, 'max_ads_per_day': 100,
        'withdrawal_commission': 1.0, 'captcha_every': 10,
        'welcome_message': '', 'welcome_active': False,
        'active_theme': 'dark_gold',
        'min_vodafone': 5, 'fee_vodafone': 1,
        'min_etisalat': 5, 'fee_etisalat': 1,
        'min_orange':   5, 'fee_orange':   1,
        'min_we':       5, 'fee_we':       1,
        'min_binance':  10,'fee_binance':  0.5,
        'min_ethereum': 20,'fee_ethereum': 2,
    }
    supabase.table('settings').insert(default).execute()
    return {k if k != 'minimum_withdraw' else 'min_withdraw': v for k,v in default.items()}

def update_settings(**kwargs) -> dict:
    # تحويل min_withdraw → minimum_withdraw
    if 'min_withdraw' in kwargs:
        kwargs['minimum_withdraw'] = kwargs.pop('min_withdraw')
    # حذف المفاتيح غير الموجودة في قاعدة البيانات
    allowed = {'reward_per_ad','minimum_withdraw','cooldown_seconds','max_ads_per_day',
               'withdrawal_commission','captcha_every','welcome_message','welcome_active',
               'active_theme','min_vodafone','fee_vodafone','min_etisalat','fee_etisalat',
               'min_orange','fee_orange','min_we','fee_we','min_binance','fee_binance',
               'min_ethereum','fee_ethereum'}
    kwargs = {k:v for k,v in kwargs.items() if k in allowed}
    r = supabase.table('settings').select('id').limit(1).execute()
    if r.data:
        supabase.table('settings').update(kwargs).eq('id', r.data[0]['id']).execute()
    return get_settings()

# ══════════════════════════════════════════════════════════════════════════════
# FEATURED BOTS
# ══════════════════════════════════════════════════════════════════════════════

def get_active_bots() -> list:
    r = supabase.table('featured_bots').select('*')\
        .eq('is_active', True)\
        .order('id', desc=True).execute()
    return r.data or []

def get_all_bots() -> list:
    r = supabase.table('featured_bots').select('*')\
        .order('id', desc=True).execute()
    return r.data or []

def create_bot(title: str, message: str, bot_link: str) -> dict:
    data = {'title': title, 'message': message, 'bot_link': bot_link, 'is_active': True}
    r = supabase.table('featured_bots').insert(data).execute()
    return r.data[0] if r.data else data

def update_bot(bot_id: int, **kwargs) -> dict | None:
    r = supabase.table('featured_bots').update(kwargs).eq('id', bot_id).execute()
    return r.data[0] if r.data else None

def delete_bot(bot_id: int):
    supabase.table('featured_bots').delete().eq('id', bot_id).execute()

def bot_to_dict(b: dict) -> dict:
    return {
        'id':         b.get('id'),
        'title':      b.get('title', ''),
        'message':    b.get('message', ''),
        'bot_link':   b.get('bot_link', ''),
        'is_active':  b.get('is_active', True),
        'created_at': fmt_date(b.get('created_at', '')),
    }

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN STATS
# ══════════════════════════════════════════════════════════════════════════════

def get_admin_stats() -> dict:
    today = datetime.utcnow().strftime('%Y-%m-%d')

    # عدد المستخدمين
    total_users = supabase.table('users').select('id', count='exact').execute().count or 0

    # إجمالي الرصيد
    bal_r  = supabase.table('users').select('balance').execute()
    total_balance = sum(float(u.get('balance') or 0) for u in (bal_r.data or []))

    # إجمالي المكتسب
    ear_r  = supabase.table('users').select('total_earned').execute()
    total_earned = sum(float(u.get('total_earned') or 0) for u in (ear_r.data or []))

    # طلبات السحب
    pending = supabase.table('withdrawals').select('id', count='exact').eq('status', 'pending').execute().count or 0
    total_w = supabase.table('withdrawals').select('id', count='exact').execute().count or 0

    # مستخدمون جدد اليوم
    new_today = supabase.table('users').select('id', count='exact')\
        .gte('join_date', today + 'T00:00:00').execute().count or 0

    sett = get_settings()
    return {
        'total_users':         total_users,
        'total_balance':       round(total_balance, 5),
        'total_earned':        round(total_earned,  5),
        'pending_withdrawals': pending,
        'total_withdrawals':   total_w,
        'new_today':           new_today,
        **sett
    }

def increment_ads_since_captcha(user_id: str) -> int:
    user = get_user(user_id)
    if not user: return 0
    new_count = (user.get('ads_since_captcha') or 0) + 1
    update_user(user_id, ads_since_captcha=new_count)
    return new_count

def reset_captcha_count(user_id: str):
    update_user(user_id, ads_since_captcha=0)

def get_top_referrers(limit: int = 50) -> list:
    r = supabase.table('users').select('user_id,username,referral_count,total_earned')\
        .gt('referral_count', 0)\
        .order('referral_count', desc=True)\
        .limit(limit).execute()
    return r.data or []
