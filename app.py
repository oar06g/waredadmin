"""
admin/app.py — لوحة تحكم الأدمن
Flask + Supabase (بدون SQLAlchemy)
PORT: 5001
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from datetime import datetime
from db import (
    get_all_users, get_user, update_user, delete_user, user_to_dict,
    get_all_withdrawals, get_withdrawal, update_withdrawal_status, withdrawal_to_dict,
    create_transaction, add_balance,
    get_settings, update_settings,
    get_admin_stats, get_top_referrers,
    get_all_bots, create_bot, update_bot, delete_bot, bot_to_dict,
)

load_dotenv()

# ── إعداد التطبيق ─────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('ADMIN_SECRET_KEY', 'admin_change_me')
ADMIN_ID = os.environ.get('ADMIN_ID', '8988236075')

# ── CORS ─────────────────────────────────────────────────────────────────────
@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin']  = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Admin-ID, ngrok-skip-browser-warning'
    r.headers['ngrok-skip-browser-warning']   = 'true'
    return r

def is_admin() -> bool:
    aid = request.headers.get('X-Admin-ID', '') or (request.json or {}).get('admin_id', '')
    return str(aid) == ADMIN_ID

def admin_only(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_admin():
            return jsonify({'error': 'غير مصرح'}), 403
        return f(*args, **kwargs)
    return wrapper

# ══════════════════════════════════════════════════════════════════════════════
# صفحات HTML
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def page_admin():
    return render_template('admin.html')

# ══════════════════════════════════════════════════════════════════════════════
# API — إحصائيات
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/stats', methods=['POST'])
@admin_only
def stats():
    return jsonify(get_admin_stats())

# ══════════════════════════════════════════════════════════════════════════════
# API — المستخدمون
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/users', methods=['POST'])
@admin_only
def users():
    d        = request.json or {}
    search   = d.get('search', '')
    page     = int(d.get('page', 1))
    rows, total, pages = get_all_users(search=search, page=page)
    return jsonify({
        'users': [user_to_dict(u) for u in rows],
        'total': total,
        'pages': pages
    })


@app.route('/api/user/edit', methods=['POST'])
@admin_only
def user_edit():
    d      = request.json or {}
    uid    = d.get('user_id', '')
    action = d.get('action', '')
    amount = float(d.get('amount', 0))

    user = get_user(uid)
    if not user:
        return jsonify({'error': 'مستخدم غير موجود'}), 404

    if action == 'delete':
        delete_user(uid)
        return jsonify({'success': True})

    balance = float(user.get('balance') or 0)
    if action == 'add':
        new_bal = round(balance + amount, 10)
        desc    = f'إضافة {amount} ج.م بواسطة الأدمن'
        tx_amt  = amount
    elif action == 'deduct':
        new_bal = round(max(0, balance - amount), 10)
        desc    = f'خصم {amount} ج.م بواسطة الأدمن'
        tx_amt  = -amount
    elif action == 'set':
        new_bal = round(amount, 10)
        desc    = f'تعيين الرصيد إلى {amount} ج.م بواسطة الأدمن'
        tx_amt  = amount - balance
    else:
        return jsonify({'error': 'إجراء غير معروف'}), 400

    update_user(uid, balance=new_bal)
    create_transaction(uid, 'admin_action', tx_amt, desc)
    return jsonify({'success': True, 'new_balance': new_bal})

# ══════════════════════════════════════════════════════════════════════════════
# API — طلبات السحب
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/withdrawals', methods=['POST'])
@admin_only
def withdrawals():
    status = (request.json or {}).get('status', 'all')
    rows   = get_all_withdrawals(status=status)
    return jsonify({'withdrawals': [withdrawal_to_dict(w) for w in rows]})


@app.route('/api/withdrawal/action', methods=['POST'])
@admin_only
def withdrawal_action():
    d      = request.json or {}
    wid    = int(d.get('withdrawal_id', 0))
    action = d.get('action', '')

    w = get_withdrawal(wid)
    if not w:
        return jsonify({'error': 'طلب غير موجود'}), 404

    if action == 'approve':
        update_withdrawal_status(wid, 'approved')
        create_transaction(
            w['user_id'], 'withdrawal_approved',
            -float(w.get('amount') or 0),
            f'تمت الموافقة على سحب {w.get("amount")} ج.م عبر {w.get("wallet_type")}'
        )

    elif action == 'reject':
        update_withdrawal_status(wid, 'rejected')
        # إعادة المبلغ + العمولة
        total  = float(w.get('amount') or 0) + float(w.get('commission') or 0)
        user   = get_user(w['user_id'])
        if user:
            update_user(w['user_id'], balance=round(float(user.get('balance') or 0) + total, 10))
        create_transaction(
            w['user_id'], 'withdrawal_rejected', total,
            f'رُفض طلب السحب — تمت إعادة {total} ج.م'
        )
    else:
        return jsonify({'error': 'إجراء غير معروف'}), 400

    return jsonify({'success': True})

# ══════════════════════════════════════════════════════════════════════════════
# API — الإعدادات
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/settings', methods=['POST'])
@admin_only
def settings():
    d     = request.json or {}
    keys  = ['reward_per_ad', 'min_withdraw', 'cooldown_seconds',
             'max_ads_per_day', 'withdrawal_commission',
             'captcha_every', 'welcome_message', 'welcome_active', 'active_theme',
             'min_vodafone', 'fee_vodafone', 'min_etisalat', 'fee_etisalat',
             'min_orange',   'fee_orange',   'min_we',       'fee_we',
             'min_binance',  'fee_binance',  'min_ethereum', 'fee_ethereum',
             'min_usdt',     'fee_usdt',     'usdt_networks','active_usdt_nets']
    patch = {k: d[k] for k in keys if k in d}
    if not patch:
        return jsonify({'error': 'لا توجد قيم للتحديث'}), 400
    result = update_settings(**patch)
    return jsonify({'success': True, **result})

# ══════════════════════════════════════════════════════════════════════════════
# API — الإحالات
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/referrals', methods=['POST'])
@admin_only
def referrals():
    rows = get_top_referrers()
    return jsonify({'referrals': rows})

# ══════════════════════════════════════════════════════════════════════════════
# API — بوتات الربح
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/bots', methods=['POST'])
@admin_only
def bots_list():
    return jsonify({'bots': [bot_to_dict(b) for b in get_all_bots()]})


@app.route('/api/bots/add', methods=['POST'])
@admin_only
def bots_add():
    d       = request.json or {}
    title   = d.get('title',    '').strip()
    message = d.get('message',  '').strip()
    link    = d.get('bot_link', '').strip()
    if not title or not message or not link:
        return jsonify({'error': 'أدخل العنوان والرسالة والرابط'}), 400
    b = create_bot(title, message, link)
    return jsonify({'success': True, 'bot': bot_to_dict(b)})


@app.route('/api/bots/edit', methods=['POST'])
@admin_only
def bots_edit():
    d   = request.json or {}
    bid = int(d.get('id', 0))
    if not bid:
        return jsonify({'error': 'id مطلوب'}), 400
    allowed = {'title', 'message', 'bot_link', 'is_active'}
    patch   = {k: v for k, v in d.items() if k in allowed}
    b = update_bot(bid, **patch)
    return jsonify({'success': True, 'bot': bot_to_dict(b) if b else {}})


@app.route('/api/bots/delete', methods=['POST'])
@admin_only
def bots_delete():
    bid = int((request.json or {}).get('id', 0))
    if not bid:
        return jsonify({'error': 'id مطلوب'}), 400
    delete_bot(bid)
    return jsonify({'success': True})

# ══════════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("🛡️  Admin → http://0.0.0.0:5001")
    app.run(host='0.0.0.0', port=5001, debug=False)
