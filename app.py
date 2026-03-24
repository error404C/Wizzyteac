import os
import sqlite3
import subprocess
import time
from functools import wraps
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "wtc-wizzy-tech-secret-2025")

BOTS_DIR = "hosted_bots"
LOG_DIR  = "logs"
os.makedirs(BOTS_DIR, exist_ok=True)
os.makedirs(LOG_DIR,  exist_ok=True)

ADMIN_EMAIL    = "adminwizzy@gmail.com"
ADMIN_PASSWORD = "admin123@"
ADMIN_USERNAME = "WizzyAdmin"

running_processes = {}

# ── Database ──────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect("wtc.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email    TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role     TEXT DEFAULT 'user',
            created  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS bots (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER NOT NULL,
            name      TEXT NOT NULL,
            file_path TEXT,
            status    TEXT DEFAULT 'stopped',
            token     TEXT DEFAULT '',
            created   TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
    """)
    existing = conn.execute("SELECT id FROM users WHERE email=?", (ADMIN_EMAIL,)).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO users (username,email,password,role) VALUES (?,?,?,?)",
            (ADMIN_USERNAME, ADMIN_EMAIL, generate_password_hash(ADMIN_PASSWORD), "admin")
        )
    else:
        conn.execute(
            "UPDATE users SET password=?, role='admin' WHERE email=?",
            (generate_password_hash(ADMIN_PASSWORD), ADMIN_EMAIL)
        )
    conn.commit()
    conn.close()

init_db()

# ── Helpers ───────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def d(*a, **kw):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return d

def admin_required(f):
    @wraps(f)
    def d(*a, **kw):
        if session.get("role") != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))
        return f(*a, **kw)
    return d

def get_current_user():
    if "user_id" not in session:
        return None
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    conn.close()
    return u

def get_bot_or_403(bot_id):
    user = get_current_user()
    conn = get_db()
    bot  = conn.execute("SELECT * FROM bots WHERE id=?", (bot_id,)).fetchone()
    conn.close()
    if not bot or (bot["user_id"] != user["id"] and user["role"] != "admin"):
        return None, None
    return bot, user

# ── Shared CSS & JS (injected into every page) ────────────────────────────
SHARED = """
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Outfit:wght@400;600;700;800&display=swap" rel="stylesheet"/>
<style>
:root{--bg:#0a0a0f;--surf:#111118;--surf2:#18181f;--bord:#2a2a35;--acc:#6c63ff;--grn:#00d4aa;--red:#ff4757;--ylw:#ffa502;--txt:#f0f0f8;--mut:#6b6b80;--mono:'Space Mono',monospace;--sans:'Outfit',sans-serif;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--txt);font-family:var(--sans);min-height:100vh;line-height:1.6;}
::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}::-webkit-scrollbar-thumb{background:var(--bord);border-radius:3px;}
nav{background:rgba(17,17,24,0.96);backdrop-filter:blur(12px);border-bottom:1px solid var(--bord);padding:0 28px;height:60px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;}
.nb{display:flex;align-items:center;gap:10px;text-decoration:none;}
.nl{width:34px;height:34px;border-radius:8px;background:linear-gradient(135deg,var(--acc),#9c35ff);display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:11px;font-weight:700;color:#fff;letter-spacing:-1px;}
.nn{font-size:16px;font-weight:700;color:var(--txt);}
.nn span{color:var(--acc);}
.nlinks{display:flex;gap:2px;}
.nlinks a{color:var(--mut);text-decoration:none;padding:7px 14px;border-radius:8px;font-size:13px;font-weight:500;transition:all .15s;}
.nlinks a:hover{color:var(--txt);background:var(--surf2);}
.nlinks a.active{color:var(--acc);background:rgba(108,99,255,.1);}
.nright{display:flex;align-items:center;gap:10px;}
.nbadge{font-family:var(--mono);font-size:11px;color:var(--mut);background:var(--surf2);border:1px solid var(--bord);padding:4px 10px;border-radius:20px;}
.nbadge.adm{color:var(--acc);border-color:rgba(108,99,255,.4);background:rgba(108,99,255,.1);}
.page{max-width:1140px;margin:0 auto;padding:36px 24px;}
.ph{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:32px;gap:16px;flex-wrap:wrap;}
.pt{font-size:24px;font-weight:800;}
.ps{font-size:13px;color:var(--mut);font-family:var(--mono);margin-top:3px;}
.srow{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:32px;}
.sc{background:var(--surf);border:1px solid var(--bord);border-radius:10px;padding:20px;display:flex;align-items:center;gap:16px;transition:border-color .2s;}
.sc:hover{border-color:var(--acc);}
.si{width:44px;height:44px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0;}
.si.p{background:rgba(108,99,255,.15);}
.si.g{background:rgba(0,212,170,.15);}
.si.r{background:rgba(255,71,87,.15);}
.sv{font-size:28px;font-weight:800;font-family:var(--mono);line-height:1;}
.sl{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.8px;margin-top:3px;font-weight:600;}
.bgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;}
.bc{background:var(--surf);border:1px solid var(--bord);border-radius:10px;padding:20px;transition:all .2s;position:relative;overflow:hidden;}
.bc:hover{border-color:rgba(108,99,255,.5);transform:translateY(-2px);box-shadow:0 8px 30px rgba(0,0,0,.3);}
.bc::after{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--bord);transition:background .2s;}
.bc.running::after{background:linear-gradient(90deg,var(--grn),#00ffcc);}
.bh{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;}
.bn{font-size:15px;font-weight:700;}
.bo{font-size:11px;color:var(--mut);font-family:var(--mono);margin-top:2px;}
.bd{font-size:11px;color:var(--mut);font-family:var(--mono);margin-bottom:16px;}
.ba{display:flex;gap:6px;flex-wrap:wrap;}
.badge{display:inline-flex;align-items:center;gap:5px;padding:4px 10px;border-radius:20px;font-size:11px;font-family:var(--mono);font-weight:700;white-space:nowrap;}
.badge.running{background:rgba(0,212,170,.15);color:var(--grn);}
.badge.stopped{background:rgba(255,71,87,.12);color:var(--red);}
.bdot{width:6px;height:6px;border-radius:50%;background:currentColor;}
.badge.running .bdot{animation:blink 1.4s infinite;}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
.btn{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;border-radius:8px;border:1px solid transparent;font-size:12px;font-weight:600;font-family:var(--mono);cursor:pointer;transition:all .15s;text-decoration:none;white-space:nowrap;}
.btn-p{background:var(--acc);color:#fff;border-color:var(--acc);}
.btn-p:hover{background:#7d75ff;}
.btn-g{background:rgba(0,212,170,.15);color:var(--grn);border-color:rgba(0,212,170,.3);}
.btn-g:hover{background:rgba(0,212,170,.25);}
.btn-r{background:rgba(255,71,87,.12);color:var(--red);border-color:rgba(255,71,87,.3);}
.btn-r:hover{background:rgba(255,71,87,.22);}
.btn-y{background:rgba(255,165,2,.12);color:var(--ylw);border-color:rgba(255,165,2,.3);}
.btn-y:hover{background:rgba(255,165,2,.22);}
.btn-gh{background:transparent;color:var(--mut);border-color:var(--bord);}
.btn-gh:hover{color:var(--txt);border-color:var(--mut);}
.btn-sm{padding:5px 11px;font-size:11px;}
.card{background:var(--surf);border:1px solid var(--bord);border-radius:10px;padding:24px;}
.fg{margin-bottom:18px;}
.fl{display:block;font-size:11px;font-weight:700;font-family:var(--mono);color:var(--mut);margin-bottom:7px;text-transform:uppercase;letter-spacing:.8px;}
.fi{width:100%;background:#0d0d14;border:1px solid var(--bord);border-radius:8px;padding:11px 14px;color:var(--txt);font-family:var(--mono);font-size:13px;outline:none;transition:border-color .15s;}
.fi:focus{border-color:var(--acc);}
.fi[type=file]{padding:18px;border:2px dashed var(--bord);color:var(--mut);cursor:pointer;text-align:center;}
.fi[type=file]:hover{border-color:var(--acc);}
.flash{padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:13px;font-family:var(--mono);border:1px solid;}
.flash.success{background:rgba(0,212,170,.1);color:var(--grn);border-color:rgba(0,212,170,.3);}
.flash.error{background:rgba(255,71,87,.1);color:var(--red);border-color:rgba(255,71,87,.3);}
.tw{border-radius:10px;overflow:hidden;border:1px solid var(--bord);}
.tb{background:var(--surf2);padding:10px 16px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--bord);}
.tdots{display:flex;gap:6px;}
.tdots span{width:11px;height:11px;border-radius:50%;}
.tdots .tr{background:#ff5f56;}.tdots .ty{background:#ffbd2e;}.tdots .tg{background:#27c93f;}
.tt{font-family:var(--mono);font-size:12px;color:var(--mut);}
.term{background:#06060a;padding:18px;font-family:var(--mono);font-size:12px;line-height:1.9;color:#4afa9a;max-height:420px;overflow-y:auto;white-space:pre-wrap;word-break:break-all;}
table{width:100%;border-collapse:collapse;font-size:13px;}
th{text-align:left;padding:10px 16px;font-family:var(--mono);font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.8px;border-bottom:1px solid var(--bord);}
td{padding:13px 16px;border-bottom:1px solid var(--bord);font-family:var(--mono);font-size:12px;}
tr:last-child td{border-bottom:none;}
tr:hover td{background:var(--surf2);}
.empty{text-align:center;padding:60px 20px;color:var(--mut);}
.empty-i{font-size:50px;margin-bottom:14px;}
.empty h3{font-size:17px;font-weight:700;color:var(--txt);margin-bottom:6px;}
#toast{position:fixed;bottom:24px;right:24px;z-index:9999;background:var(--surf2);border:1px solid var(--bord);border-radius:10px;padding:13px 20px;font-family:var(--mono);font-size:13px;color:var(--txt);transform:translateY(80px);opacity:0;transition:all .3s;pointer-events:none;min-width:200px;}
#toast.show{transform:translateY(0);opacity:1;}
#toast.ok{border-color:var(--grn);color:var(--grn);}
#toast.err{border-color:var(--red);color:var(--red);}
.mo{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:200;align-items:center;justify-content:center;}
.mo.open{display:flex;}
.mb{background:var(--surf);border:1px solid var(--bord);border-radius:10px;padding:30px;width:100%;max-width:400px;animation:popIn .2s ease;}
@keyframes popIn{from{transform:scale(.94);opacity:0}to{transform:scale(1);opacity:1}}
.mb h3{font-size:17px;font-weight:700;margin-bottom:14px;}
.ma{display:flex;gap:8px;justify-content:flex-end;margin-top:22px;}
.bg-orb{position:fixed;border-radius:50%;filter:blur(80px);pointer-events:none;opacity:.4;}
.o1{width:400px;height:400px;background:radial-gradient(circle,rgba(108,99,255,.3),transparent);top:-100px;left:-100px;animation:drift 8s ease-in-out infinite alternate;}
.o2{width:300px;height:300px;background:radial-gradient(circle,rgba(0,212,170,.2),transparent);bottom:-80px;right:-80px;animation:drift 10s ease-in-out infinite alternate-reverse;}
@keyframes drift{0%{transform:translate(0,0)}100%{transform:translate(40px,30px)}}
.grid-bg::before{content:'';position:fixed;inset:0;background-image:linear-gradient(var(--bord) 1px,transparent 1px),linear-gradient(90deg,var(--bord) 1px,transparent 1px);background-size:50px 50px;opacity:.25;pointer-events:none;}
@media(max-width:640px){.srow{grid-template-columns:1fr;}.bgrid{grid-template-columns:1fr;}.ph{flex-direction:column;}nav{padding:0 14px;}.nlinks a{padding:6px 8px;}}
</style>
<script>
function toast(msg,type='ok'){const t=document.getElementById('toast');t.textContent=msg;t.className='show '+type;setTimeout(()=>t.className='',3000);}
async function apiCall(url,method='POST',body=null){const o={method,headers:{'Content-Type':'application/json'}};if(body)o.body=JSON.stringify(body);const r=await fetch(url,o);return r.json();}
</script>
"""

NAV = """
<nav>
  <a class="nb" href="/dashboard">
    <div class="nl">WTC</div>
    <span class="nn">Wizzy<span>Tech</span> Host</span>
  </a>
  <div class="nlinks">
    <a href="/dashboard" class="{{ 'active' if active=='dashboard' else '' }}">Dashboard</a>
    <a href="/upload"    class="{{ 'active' if active=='upload' else '' }}">Upload</a>
    {% if session.role == 'admin' %}
    <a href="/admin"     class="{{ 'active' if active=='admin' else '' }}">Admin</a>
    {% endif %}
  </div>
  <div class="nright">
    <span class="nbadge {{ 'adm' if session.role=='admin' else '' }}">
      {% if session.role=='admin' %}👑 {% endif %}{{ session.username }}
    </span>
    <a href="/logout" class="btn btn-gh btn-sm">Sign out</a>
  </div>
</nav>
<div id="toast"></div>
"""

# ── Page templates ─────────────────────────────────────────────────────────

LOGIN_HTML = """<!DOCTYPE html><html><head>{{ shared|safe }}<title>Sign In — WTC Host</title></head>
<body class="grid-bg" style="display:flex;align-items:center;justify-content:center;">
<div class="bg-orb o1"></div><div class="bg-orb o2"></div>
<div style="position:relative;z-index:1;width:100%;max-width:400px;padding:20px;">
  <div style="background:rgba(17,17,24,.95);border:1px solid var(--bord);border-radius:16px;padding:44px 40px;backdrop-filter:blur(20px);box-shadow:0 30px 80px rgba(0,0,0,.6);">
    <div style="text-align:center;margin-bottom:36px;">
      <div style="width:60px;height:60px;border-radius:14px;background:linear-gradient(135deg,var(--acc),#9c35ff);display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:16px;font-weight:700;color:#fff;margin:0 auto 14px;letter-spacing:-1px;box-shadow:0 8px 24px rgba(108,99,255,.4);">WTC</div>
      <h1 style="font-size:20px;font-weight:800;">Wizzy<span style="color:var(--acc);">Tech</span> Host</h1>
      <p style="font-size:12px;color:var(--mut);font-family:var(--mono);margin-top:4px;">// telegram bot hosting panel</p>
    </div>
    {% for cat,msg in messages %}<div class="flash {{cat}}">{{msg}}</div>{% endfor %}
    <form method="POST">
      <div class="fg"><label class="fl">Email Address</label><input class="fi" type="email" name="email" placeholder="you@email.com" required autofocus/></div>
      <div class="fg"><label class="fl">Password</label><input class="fi" type="password" name="password" placeholder="••••••••" required/></div>
      <button type="submit" style="width:100%;padding:13px;border-radius:8px;border:none;background:linear-gradient(135deg,var(--acc),#9c35ff);color:#fff;font-family:var(--sans);font-size:15px;font-weight:700;cursor:pointer;box-shadow:0 4px 20px rgba(108,99,255,.4);margin-top:6px;">Sign In →</button>
    </form>
    <p style="text-align:center;margin-top:22px;font-size:12px;color:var(--mut);font-family:var(--mono);">No account? <a href="/register" style="color:var(--acc);">Create one free</a></p>
  </div>
</div></body></html>"""

REGISTER_HTML = """<!DOCTYPE html><html><head>{{ shared|safe }}<title>Register — WTC Host</title></head>
<body class="grid-bg" style="display:flex;align-items:center;justify-content:center;">
<div class="bg-orb o1"></div><div class="bg-orb o2"></div>
<div style="position:relative;z-index:1;width:100%;max-width:420px;padding:20px;">
  <div style="background:rgba(17,17,24,.95);border:1px solid var(--bord);border-radius:16px;padding:40px;backdrop-filter:blur(20px);box-shadow:0 30px 80px rgba(0,0,0,.6);">
    <div style="text-align:center;margin-bottom:30px;">
      <div style="width:52px;height:52px;border-radius:12px;background:linear-gradient(135deg,var(--acc),#9c35ff);display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:14px;font-weight:700;color:#fff;margin:0 auto 12px;letter-spacing:-1px;box-shadow:0 8px 24px rgba(108,99,255,.4);">WTC</div>
      <h1 style="font-size:19px;font-weight:800;">Wizzy<span style="color:var(--acc);">Tech</span> Host</h1>
      <p style="font-size:12px;color:var(--mut);font-family:var(--mono);margin-top:4px;">// create your free account</p>
    </div>
    {% for cat,msg in messages %}<div class="flash {{cat}}">{{msg}}</div>{% endfor %}
    <form method="POST">
      <div class="fg"><label class="fl">Username</label><input class="fi" type="text" name="username" placeholder="your_username" required autofocus/></div>
      <div class="fg"><label class="fl">Email</label><input class="fi" type="email" name="email" placeholder="you@email.com" required/></div>
      <div class="fg"><label class="fl">Password</label><input class="fi" type="password" name="password" placeholder="••••••••" required/>
        <p style="font-size:11px;color:var(--mut);font-family:var(--mono);margin-top:5px;">// min 6 characters</p></div>
      <div class="fg"><label class="fl">Confirm Password</label><input class="fi" type="password" name="confirm" placeholder="••••••••" required/></div>
      <button type="submit" style="width:100%;padding:13px;border-radius:8px;border:none;background:linear-gradient(135deg,var(--acc),#9c35ff);color:#fff;font-family:var(--sans);font-size:15px;font-weight:700;cursor:pointer;box-shadow:0 4px 20px rgba(108,99,255,.4);margin-top:6px;">Create Account →</button>
    </form>
    <p style="text-align:center;margin-top:20px;font-size:12px;color:var(--mut);font-family:var(--mono);">Have an account? <a href="/login" style="color:var(--acc);">Sign in</a></p>
  </div>
</div></body></html>"""

DASHBOARD_HTML = """<!DOCTYPE html><html><head>{{ shared|safe }}<title>Dashboard — WTC Host</title></head><body>
{{ nav|safe }}
<div class="page">
  {% for cat,msg in messages %}<div class="flash {{cat}}">{{msg}}</div>{% endfor %}
  <div class="ph">
    <div>
      <div class="pt">{% if user.role=='admin' %}👑 {% endif %}Dashboard</div>
      <div class="ps">// welcome back, {{user.username}}{% if user.role=='admin' %} · all bots{% endif %}</div>
    </div>
    <a href="/upload" class="btn btn-p">+ Upload Bot</a>
  </div>
  <div class="srow">
    <div class="sc"><div class="si p">🤖</div><div><div class="sv">{{stats.total}}</div><div class="sl">Total Bots</div></div></div>
    <div class="sc"><div class="si g">▶</div><div><div class="sv" style="color:var(--grn)">{{stats.running}}</div><div class="sl">Running</div></div></div>
    <div class="sc"><div class="si r">⏹</div><div><div class="sv" style="color:var(--red)">{{stats.stopped}}</div><div class="sl">Stopped</div></div></div>
  </div>
  {% if bots %}
  <div class="bgrid">
    {% for b in bots %}
    <div class="bc {{b.status}}" id="card-{{b.id}}">
      <div class="bh">
        <div><div class="bn">{{b.name}}</div><div class="bo">@{{b.username}}</div></div>
        <span class="badge {{b.status}}" id="badge-{{b.id}}"><span class="bdot"></span>{{b.status}}</span>
      </div>
      <div class="bd">// {{b.created[:10]}}</div>
      <div class="ba">
        <button class="btn btn-g btn-sm" onclick="startBot({{b.id}})">▶ Start</button>
        <button class="btn btn-r btn-sm" onclick="stopBot({{b.id}})">⏹ Stop</button>
        <button class="btn btn-y btn-sm" onclick="restartBot({{b.id}})">↺ Restart</button>
        <a href="/bot/{{b.id}}" class="btn btn-gh btn-sm">Manage →</a>
        <button class="btn btn-r btn-sm" onclick="openDel({{b.id}},'{{b.name}}')">🗑</button>
      </div>
    </div>
    {% endfor %}
  </div>
  {% else %}
  <div class="empty"><div class="empty-i">🤖</div><h3>No bots yet</h3><p>// upload your first .py bot to get started</p><br/><a href="/upload" class="btn btn-p" style="display:inline-flex;width:auto;">+ Upload Bot</a></div>
  {% endif %}
</div>
<div class="mo" id="delMo">
  <div class="mb">
    <h3>🗑 Delete Bot</h3>
    <p style="font-size:13px;color:var(--mut);font-family:var(--mono);margin-top:8px;">Delete <strong id="delN"></strong>? Stops the process and removes all files.</p>
    <div class="ma"><button class="btn btn-gh" onclick="closeDel()">Cancel</button><button class="btn btn-r" id="delBtn">Delete</button></div>
  </div>
</div>
<script>
let pid=null;
function updateCard(id,s){const c=document.getElementById('card-'+id),b=document.getElementById('badge-'+id);if(!c||!b)return;c.className='bc '+s;b.className='badge '+s;b.innerHTML='<span class="bdot"></span>'+s;}
async function startBot(id){toast('Starting...','ok');const r=await apiCall('/api/bot/'+id+'/start');r.ok?(updateCard(id,'running'),toast('Started ✓','ok')):toast(r.error||'Failed','err');}
async function stopBot(id){toast('Stopping...','ok');const r=await apiCall('/api/bot/'+id+'/stop');r.ok?(updateCard(id,'stopped'),toast('Stopped','ok')):toast(r.error||'Failed','err');}
async function restartBot(id){toast('Restarting...','ok');await apiCall('/api/bot/'+id+'/stop');await new Promise(r=>setTimeout(r,900));const r=await apiCall('/api/bot/'+id+'/start');r.ok?(updateCard(id,'running'),toast('Restarted ✓','ok')):toast('Failed','err');}
function openDel(id,n){pid=id;document.getElementById('delN').textContent=n;document.getElementById('delMo').classList.add('open');}
function closeDel(){document.getElementById('delMo').classList.remove('open');pid=null;}
document.getElementById('delBtn').addEventListener('click',async()=>{if(!pid)return;const r=await apiCall('/api/bot/'+pid+'/delete');if(r.ok){document.getElementById('card-'+pid)?.remove();toast('Deleted','ok');closeDel();}else toast('Failed','err');});
document.getElementById('delMo').addEventListener('click',e=>{if(e.target===e.currentTarget)closeDel();});
</script></body></html>"""

UPLOAD_HTML = """<!DOCTYPE html><html><head>{{ shared|safe }}<title>Upload — WTC Host</title></head><body>
{{ nav|safe }}
<div class="page" style="max-width:620px">
  <div class="ph">
    <div><div class="pt">Upload Bot</div><div class="ps">// deploy a new python bot</div></div>
    <a href="/dashboard" class="btn btn-gh">← Back</a>
  </div>
  {% for cat,msg in messages %}<div class="flash {{cat}}">{{msg}}</div>{% endfor %}
  <div class="card">
    <form method="POST" enctype="multipart/form-data">
      <div class="fg"><label class="fl">Bot Name</label><input class="fi" type="text" name="name" placeholder="My Telegram Bot" required/></div>
      <div class="fg"><label class="fl">Bot Token <span style="color:var(--mut);font-weight:400;">(optional)</span></label><input class="fi" type="text" name="token" placeholder="1234567890:AAxxxxxxxx"/></div>
      <div class="fg"><label class="fl">Bot File (.py only)</label><input class="fi" type="file" name="file" accept=".py" required/></div>
      <div style="background:rgba(108,99,255,.07);border:1px solid rgba(108,99,255,.2);border-radius:8px;padding:14px;margin-bottom:22px;font-family:var(--mono);font-size:12px;color:var(--mut);line-height:2;">
        <span style="color:var(--acc);font-weight:700;">// notes</span><br/>
        → Only <span style="color:var(--grn)">.py</span> files accepted<br/>
        → Bot runs as a subprocess on the server<br/>
        → Token can be hardcoded in the file or set here
      </div>
      <button type="submit" class="btn btn-p" style="padding:11px 28px;">📤 Upload & Deploy</button>
    </form>
  </div>
</div></body></html>"""

BOT_DETAIL_HTML = """<!DOCTYPE html><html><head>{{ shared|safe }}<title>{{bot.name}} — WTC Host</title></head><body>
{{ nav|safe }}
<div class="page">
  <div class="ph">
    <div>
      <div class="pt" style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
        {{bot.name}}
        <span class="badge {{bot.status}}" id="mbadge"><span class="bdot"></span>{{bot.status}}</span>
      </div>
      <div class="ps">// bot #{{bot.id}} · {{bot.created[:10]}}</div>
    </div>
    <a href="/dashboard" class="btn btn-gh">← Dashboard</a>
  </div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:28px;">
    <button class="btn btn-g" onclick="startBot()">▶ Start</button>
    <button class="btn btn-r" onclick="stopBot()">⏹ Stop</button>
    <button class="btn btn-y" onclick="restartBot()">↺ Restart</button>
    <button class="btn btn-gh" onclick="refreshLogs()">⟳ Refresh</button>
    <button class="btn btn-gh" onclick="clearLogs()">🗑 Clear Logs</button>
  </div>
  <div style="display:grid;grid-template-columns:1fr 320px;gap:20px;align-items:start;">
    <div>
      <div class="tw">
        <div class="tb">
          <div class="tdots"><span class="tr"></span><span class="ty"></span><span class="tg"></span></div>
          <span class="tt">{{bot.name}}.log</span>
          <span id="lts" style="font-family:var(--mono);font-size:11px;color:var(--mut);">auto 5s</span>
        </div>
        <div class="term" id="logbox">{{log or '// no logs yet'}}</div>
      </div>
    </div>
    <div style="display:flex;flex-direction:column;gap:14px;">
      <div class="card">
        <div style="font-size:11px;font-weight:700;font-family:var(--mono);color:var(--mut);text-transform:uppercase;letter-spacing:.8px;margin-bottom:12px;">Bot Token</div>
        <input class="fi" type="text" id="tkval" value="{{bot.token or ''}}" placeholder="1234567890:AAx" style="margin-bottom:10px;"/>
        <button class="btn btn-p btn-sm" onclick="saveToken()">Save Token</button>
      </div>
      <div class="card">
        <div style="font-size:11px;font-weight:700;font-family:var(--mono);color:var(--mut);text-transform:uppercase;letter-spacing:.8px;margin-bottom:12px;">Info</div>
        <div style="font-family:var(--mono);font-size:12px;color:var(--mut);line-height:2.2;">
          <div>ID: <span style="color:var(--txt)">#{{bot.id}}</span></div>
          <div>Uploaded: <span style="color:var(--txt)">{{bot.created[:16]}}</span></div>
        </div>
      </div>
      <div class="card" style="border-color:rgba(255,71,87,.3);">
        <div style="font-size:11px;font-weight:700;font-family:var(--mono);color:var(--red);text-transform:uppercase;letter-spacing:.8px;margin-bottom:10px;">⚠ Danger Zone</div>
        <p style="font-size:12px;color:var(--mut);font-family:var(--mono);margin-bottom:12px;line-height:1.7;">Stop and permanently delete this bot.</p>
        <button class="btn btn-r btn-sm" onclick="openDel()">🗑 Delete Bot</button>
      </div>
    </div>
  </div>
</div>
<div class="mo" id="delMo">
  <div class="mb">
    <h3>🗑 Delete Bot</h3>
    <p style="font-size:13px;color:var(--mut);font-family:var(--mono);margin:10px 0 20px;line-height:1.7;">Delete <strong>{{bot.name}}</strong>? This cannot be undone.</p>
    <div class="ma"><button class="btn btn-gh" onclick="closeDel()">Cancel</button><button class="btn btn-r" onclick="confirmDel()">Delete Forever</button></div>
  </div>
</div>
<script>
const BID={{bot.id}};
function ub(s){const b=document.getElementById('mbadge');b.className='badge '+s;b.innerHTML='<span class="bdot"></span>'+s;}
async function startBot(){toast('Starting...','ok');const r=await apiCall('/api/bot/'+BID+'/start');r.ok?(ub('running'),toast('Started ✓','ok')):toast(r.error||'Failed','err');}
async function stopBot(){toast('Stopping...','ok');const r=await apiCall('/api/bot/'+BID+'/stop');r.ok?(ub('stopped'),toast('Stopped','ok')):toast(r.error||'Failed','err');}
async function restartBot(){toast('Restarting...','ok');await apiCall('/api/bot/'+BID+'/stop');await new Promise(r=>setTimeout(r,900));const r=await apiCall('/api/bot/'+BID+'/start');r.ok?(ub('running'),toast('Restarted ✓','ok'),refreshLogs()):toast('Failed','err');}
async function refreshLogs(){const r=await fetch('/api/bot/'+BID+'/logs');const d=await r.json();if(d.ok){const b=document.getElementById('logbox');b.textContent=d.logs||'// no logs yet';b.scrollTop=b.scrollHeight;document.getElementById('lts').textContent='updated '+new Date().toLocaleTimeString();}}
async function clearLogs(){const r=await apiCall('/api/bot/'+BID+'/clear_logs');if(r.ok){document.getElementById('logbox').textContent='// logs cleared';toast('Cleared','ok');}}
async function saveToken(){const t=document.getElementById('tkval').value.trim();const r=await apiCall('/api/bot/'+BID+'/token','POST',{token:t});r.ok?toast('Token saved ✓','ok'):toast('Failed','err');}
function openDel(){document.getElementById('delMo').classList.add('open');}
function closeDel(){document.getElementById('delMo').classList.remove('open');}
async function confirmDel(){const r=await apiCall('/api/bot/'+BID+'/delete');if(r.ok){toast('Deleted','ok');setTimeout(()=>window.location='/',800);}else toast('Failed','err');}
document.getElementById('delMo').addEventListener('click',e=>{if(e.target===e.currentTarget)closeDel();});
setInterval(refreshLogs,5000);
window.addEventListener('load',()=>{const b=document.getElementById('logbox');b.scrollTop=b.scrollHeight;});
</script></body></html>"""

ADMIN_HTML = """<!DOCTYPE html><html><head>{{ shared|safe }}<title>Admin — WTC Host</title></head><body>
{{ nav|safe }}
<div class="page">
  <div class="ph">
    <div><div class="pt">👑 Admin Panel</div><div class="ps">// user & bot management</div></div>
  </div>
  <div class="srow" style="margin-bottom:28px;">
    <div class="sc"><div class="si p">👤</div><div><div class="sv">{{users|length}}</div><div class="sl">Users</div></div></div>
    <div class="sc"><div class="si g">🤖</div><div><div class="sv">{{bots|length}}</div><div class="sl">Total Bots</div></div></div>
    <div class="sc"><div class="si r">▶</div><div><div class="sv" style="color:var(--grn)">{{bots|selectattr('status','eq','running')|list|length}}</div><div class="sl">Running</div></div></div>
  </div>
  <div class="card" style="margin-bottom:20px;">
    <div style="font-size:11px;font-weight:700;font-family:var(--mono);color:var(--mut);text-transform:uppercase;letter-spacing:.8px;margin-bottom:16px;">All Users ({{users|length}})</div>
    {% if users %}
    <table>
      <thead><tr><th>#</th><th>Username</th><th>Email</th><th>Role</th><th>Joined</th><th>Actions</th></tr></thead>
      <tbody>
        {% for u in users %}
        <tr id="ur-{{u.id}}">
          <td style="color:var(--mut)">{{u.id}}</td>
          <td><strong>{{u.username}}</strong></td>
          <td style="color:var(--mut)">{{u.email}}</td>
          <td><span style="padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;{{'background:rgba(108,99,255,.15);color:var(--acc);' if u.role=='admin' else 'background:var(--surf2);color:var(--mut);'}}">{% if u.role=='admin' %}👑 {% endif %}{{u.role}}</span></td>
          <td style="color:var(--mut)">{{u.created[:10]}}</td>
          <td><div style="display:flex;gap:6px;">
            {% if u.role!='admin' %}<button class="btn btn-gh btn-sm" onclick="promote({{u.id}})">↑ Promote</button>{% endif %}
            {% if u.email!='adminwizzy@gmail.com' %}<button class="btn btn-r btn-sm" onclick="delUser({{u.id}})">🗑</button>{% endif %}
          </div></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}<div class="empty" style="padding:30px"><div class="empty-i">👤</div><h3>No users</h3></div>{% endif %}
  </div>
  <div class="card">
    <div style="font-size:11px;font-weight:700;font-family:var(--mono);color:var(--mut);text-transform:uppercase;letter-spacing:.8px;margin-bottom:16px;">All Bots ({{bots|length}})</div>
    {% if bots %}
    <table>
      <thead><tr><th>#</th><th>Name</th><th>Owner</th><th>Status</th><th>Uploaded</th><th></th></tr></thead>
      <tbody>
        {% for b in bots %}
        <tr>
          <td style="color:var(--mut)">{{b.id}}</td>
          <td><strong>{{b.name}}</strong></td>
          <td style="color:var(--mut)">@{{b.username}}</td>
          <td><span class="badge {{b.status}}" style="font-size:11px;"><span class="bdot"></span>{{b.status}}</span></td>
          <td style="color:var(--mut)">{{b.created[:10]}}</td>
          <td><a href="/bot/{{b.id}}" class="btn btn-gh btn-sm">Manage →</a></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}<div class="empty" style="padding:30px"><div class="empty-i">🤖</div><h3>No bots</h3></div>{% endif %}
  </div>
</div>
<script>
async function promote(id){const r=await apiCall('/admin/promote/'+id);r.ok?(toast('Promoted ✓','ok'),setTimeout(()=>location.reload(),800)):toast('Failed','err');}
async function delUser(id){if(!confirm('Delete this user and all their bots?'))return;const r=await apiCall('/admin/delete_user/'+id);if(r.ok){document.getElementById('ur-'+id)?.remove();toast('Deleted','ok');}else toast(r.error||'Failed','err');}
</script></body></html>"""

# ── Route helpers ─────────────────────────────────────────────────────────
def render(template, **ctx):
    ctx["shared"] = SHARED
    ctx["messages"] = []
    with app.test_request_context():
        pass
    return render_template_string(template, **ctx)

def render_with_nav(template, active="", **ctx):
    ctx["shared"] = SHARED
    ctx["nav"]    = NAV
    ctx["active"] = active
    ctx["messages"] = []
    return render_template_string(template, **ctx)

def get_flashed():
    from flask import get_flashed_messages
    return get_flashed_messages(with_categories=True)

# ── Auth Routes ───────────────────────────────────────────────────────────
@app.route("/")
def index():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email    = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE LOWER(email)=?", (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password"], password):
            session["user_id"]  = user["id"]
            session["username"] = user["username"]
            session["role"]     = user["role"]
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template_string(LOGIN_HTML, shared=SHARED, messages=get_flashed())

@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username","").strip()
        email    = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        confirm  = request.form.get("confirm","")
        if not username or not email or not password:
            flash("All fields are required.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif email == ADMIN_EMAIL.lower():
            flash("That email is not available.", "error")
        else:
            try:
                conn = get_db()
                conn.execute("INSERT INTO users (username,email,password) VALUES (?,?,?)",
                             (username, email, generate_password_hash(password)))
                conn.commit(); conn.close()
                flash("Account created! Please sign in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("Username or email already taken.", "error")
    return render_template_string(REGISTER_HTML, shared=SHARED, messages=get_flashed())

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ── Dashboard ─────────────────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    conn = get_db()
    if user["role"] == "admin":
        bots = conn.execute("SELECT b.*,u.username FROM bots b JOIN users u ON b.user_id=u.id ORDER BY b.created DESC").fetchall()
    else:
        bots = conn.execute("SELECT b.*,u.username FROM bots b JOIN users u ON b.user_id=u.id WHERE b.user_id=? ORDER BY b.created DESC", (user["id"],)).fetchall()
    stats = {"total": len(bots), "running": sum(1 for b in bots if b["status"]=="running"), "stopped": sum(1 for b in bots if b["status"]=="stopped")}
    conn.close()
    return render_template_string(DASHBOARD_HTML, shared=SHARED, nav=NAV, active="dashboard", messages=get_flashed(), bots=bots, stats=stats, user=user)

# ── Upload ────────────────────────────────────────────────────────────────
@app.route("/upload", methods=["GET","POST"])
@login_required
def upload():
    user = get_current_user()
    if request.method == "POST":
        name  = request.form.get("name","").strip()
        token = request.form.get("token","").strip()
        file  = request.files.get("file")
        if not name:
            flash("Bot name is required.", "error")
        elif not file or not file.filename.endswith(".py"):
            flash("Please upload a valid .py file.", "error")
        else:
            filename  = secure_filename(file.filename)
            save_path = os.path.join(BOTS_DIR, f"u{user['id']}_{filename}")
            file.save(save_path)
            conn = get_db()
            conn.execute("INSERT INTO bots (user_id,name,file_path,token) VALUES (?,?,?,?)", (user["id"], name, save_path, token))
            conn.commit(); conn.close()
            flash(f'"{name}" uploaded!', "success")
            return redirect(url_for("dashboard"))
    return render_template_string(UPLOAD_HTML, shared=SHARED, nav=NAV, active="upload", messages=get_flashed(), user=user)

# ── Bot Detail ────────────────────────────────────────────────────────────
@app.route("/bot/<int:bot_id>")
@login_required
def bot_detail(bot_id):
    user = get_current_user()
    conn = get_db()
    bot  = conn.execute("SELECT * FROM bots WHERE id=?", (bot_id,)).fetchone()
    conn.close()
    if not bot:
        flash("Bot not found.", "error"); return redirect(url_for("dashboard"))
    if bot["user_id"] != user["id"] and user["role"] != "admin":
        flash("Access denied.", "error"); return redirect(url_for("dashboard"))
    log_path = f"{LOG_DIR}/{bot_id}.log"
    log = open(log_path).read()[-8000:] if os.path.exists(log_path) else ""
    return render_template_string(BOT_DETAIL_HTML, shared=SHARED, nav=NAV, active="", messages=get_flashed(), bot=bot, log=log, user=user)

# ── Bot API ───────────────────────────────────────────────────────────────
@app.route("/api/bot/<int:bot_id>/start", methods=["POST"])
@login_required
def api_start(bot_id):
    bot, user = get_bot_or_403(bot_id)
    if not bot: return jsonify({"ok":False,"error":"Access denied"}), 403
    if bot_id in running_processes: return jsonify({"ok":False,"error":"Already running"})
    log_file = open(f"{LOG_DIR}/{bot_id}.log", "a")
    process  = subprocess.Popen(["python3","-u",bot["file_path"]], stdout=log_file, stderr=log_file, env=os.environ.copy())
    running_processes[bot_id] = (process, log_file)
    conn = get_db(); conn.execute("UPDATE bots SET status='running' WHERE id=?", (bot_id,)); conn.commit(); conn.close()
    return jsonify({"ok":True,"status":"running"})

@app.route("/api/bot/<int:bot_id>/stop", methods=["POST"])
@login_required
def api_stop(bot_id):
    bot, user = get_bot_or_403(bot_id)
    if not bot: return jsonify({"ok":False,"error":"Access denied"}), 403
    proc = running_processes.pop(bot_id, None)
    if proc: proc[0].kill(); proc[1].close()
    conn = get_db(); conn.execute("UPDATE bots SET status='stopped' WHERE id=?", (bot_id,)); conn.commit(); conn.close()
    return jsonify({"ok":True,"status":"stopped"})

@app.route("/api/bot/<int:bot_id>/restart", methods=["POST"])
@login_required
def api_restart(bot_id):
    api_stop(bot_id); time.sleep(1); return api_start(bot_id)

@app.route("/api/bot/<int:bot_id>/logs")
@login_required
def api_logs(bot_id):
    bot, user = get_bot_or_403(bot_id)
    if not bot: return jsonify({"ok":False}), 403
    log_path = f"{LOG_DIR}/{bot_id}.log"
    content  = open(log_path).read()[-6000:] if os.path.exists(log_path) else "No logs yet."
    return jsonify({"ok":True,"logs":content})

@app.route("/api/bot/<int:bot_id>/clear_logs", methods=["POST"])
@login_required
def api_clear_logs(bot_id):
    bot, user = get_bot_or_403(bot_id)
    if not bot: return jsonify({"ok":False}), 403
    open(f"{LOG_DIR}/{bot_id}.log","w").close()
    return jsonify({"ok":True})

@app.route("/api/bot/<int:bot_id>/token", methods=["POST"])
@login_required
def api_token(bot_id):
    bot, user = get_bot_or_403(bot_id)
    if not bot: return jsonify({"ok":False}), 403
    conn = get_db(); conn.execute("UPDATE bots SET token=? WHERE id=?", (request.json.get("token",""), bot_id)); conn.commit(); conn.close()
    return jsonify({"ok":True})

@app.route("/api/bot/<int:bot_id>/delete", methods=["POST"])
@login_required
def api_delete(bot_id):
    bot, user = get_bot_or_403(bot_id)
    if not bot: return jsonify({"ok":False}), 403
    proc = running_processes.pop(bot_id, None)
    if proc: proc[0].kill(); proc[1].close()
    if bot["file_path"] and os.path.exists(bot["file_path"]): os.remove(bot["file_path"])
    log_path = f"{LOG_DIR}/{bot_id}.log"
    if os.path.exists(log_path): os.remove(log_path)
    conn = get_db(); conn.execute("DELETE FROM bots WHERE id=?", (bot_id,)); conn.commit(); conn.close()
    return jsonify({"ok":True})

# ── Admin ─────────────────────────────────────────────────────────────────
@app.route("/admin")
@login_required
@admin_required
def admin_panel():
    user  = get_current_user()
    conn  = get_db()
    users = conn.execute("SELECT * FROM users ORDER BY created DESC").fetchall()
    bots  = conn.execute("SELECT b.*,u.username FROM bots b JOIN users u ON b.user_id=u.id ORDER BY b.created DESC").fetchall()
    conn.close()
    return render_template_string(ADMIN_HTML, shared=SHARED, nav=NAV, active="admin", messages=get_flashed(), users=users, bots=bots, user=user)

@app.route("/admin/promote/<int:uid>", methods=["POST"])
@login_required
@admin_required
def promote_user(uid):
    conn = get_db(); conn.execute("UPDATE users SET role='admin' WHERE id=?", (uid,)); conn.commit(); conn.close()
    return jsonify({"ok":True})

@app.route("/admin/delete_user/<int:uid>", methods=["POST"])
@login_required
@admin_required
def delete_user(uid):
    conn = get_db()
    u = conn.execute("SELECT email FROM users WHERE id=?", (uid,)).fetchone()
    if u and u["email"] == ADMIN_EMAIL:
        conn.close(); return jsonify({"ok":False,"error":"Cannot delete admin"})
    conn.execute("DELETE FROM bots WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit(); conn.close()
    return jsonify({"ok":True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
