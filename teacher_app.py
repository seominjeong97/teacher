"""선생님의 작은 교무실 — Streamlit + GitHub
실행: streamlit run teacher_app.py
GitHub에는 이 파일과 requirements.txt만 올리고 Streamlit Community Cloud에서 배포.
Settings > Secrets에 아래 TOML 설정. 비밀번호와 키를 GitHub에 올리지 마세요.

[app]
url = "https://YOUR-APP.streamlit.app"

[teachers.teacher1]
name = "김 선생님"
password = "충분히-긴-첫번째-개인비밀번호"
classes = ["1학년 1반", "1학년 2반", "1학년 3반"]
subjects = ["국어"]

[teachers.teacher2]
name = "이 선생님"
password = "충분히-긴-두번째-개인비밀번호"
classes = ["2학년 1반", "2학년 2반"]
subjects = ["수학"]

[supabase]
url = "https://YOUR-PROJECT.supabase.co"
service_role_key = "YOUR-SERVER-ONLY-KEY"

Supabase SQL Editor에서 한 번 실행:
create table public.teacher_records (
 id text primary key,
 owner text not null,
 kind text not null check(kind in ('lesson','task')),
 payload jsonb not null,
 version integer not null default 1,
 created_at timestamptz not null default now()
);
create index teacher_records_owner_idx on public.teacher_records(owner,kind);
alter table public.teacher_records enable row level security;
revoke all on public.teacher_records from anon, authenticated;

서버는 개인 로그인 후 owner 조건을 강제해 계정별로 조회/수정/삭제를 분리합니다.
service_role_key는 모든 자료에 접근 가능한 서버 비밀 키로 외부에 공개하지 마세요.
운영자는 데이터베이스에서 모든 기록에 접근할 수 있습니다.
계정 ID(teacher1 등)는 기록 소유자 식별자이므로 사용 중 바꾸지 마세요.
Supabase가 없으면 SQLite 체험 모드: Cloud 재시작/재배포 시 데이터 소실 가능.
서로 다른 계정의 비밀번호는 서로 다르게 설정하세요.
학생 이름/성적/상담/건강 정보를 입력하지 않는 개인 수업·업무 보조 앱입니다.
학교 공식 시스템/자동 알림 서비스가 아니며 마감은 앱을 열어 확인합니다.
QR은 주소만 담습니다. 로그인 없이 기록을 볼 수 없습니다.
"""
import calendar
import csv
import hashlib
import hmac
import html
import io
import json
import sqlite3
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import qrcode
import requests
import streamlit as st

st.set_page_config(page_title='선생님의 작은 교무실', page_icon='🌷', layout='centered', initial_sidebar_state='collapsed')
KST = ZoneInfo('Asia/Seoul')
TODAY = datetime.now(KST).date()

def secret(section):
    try:
        return dict(st.secrets.get(section, {}))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return {}

teachers = secret('teachers')
sb, app = secret('supabase'), secret('app')
remote = bool(sb.get('url') and sb.get('service_role_key'))

st.markdown('''<style>
:root{--ink:#344843;--muted:#65766d;--mint:#dfefe6;--lavender:#ece6f5;--cream:#fbf8f1;--peach:#f8e5d9;}
#MainMenu,footer{visibility:hidden} header{background:transparent!important}
[data-testid="stAppViewContainer"]{background:var(--cream);color:var(--ink)}
.block-container{max-width:930px;padding:1.2rem 1rem 1.5rem!important}
[data-testid="stVerticalBlock"]{gap:.7rem}
h1{font-size:1.85rem!important;font-weight:750!important;letter-spacing:-1px;padding:0!important;color:var(--ink)!important}
h2{font-size:1.2rem!important;color:var(--ink)!important} h3{font-size:1.04rem!important}
p,label{color:var(--ink)} input,textarea{font-size:16px!important}
.stButton button,.stFormSubmitButton button,.stDownloadButton button{border-radius:13px;min-height:41px;font-weight:600}
button[kind="primary"]{background:#44745e!important;color:white!important;border:0!important}
[data-testid="stForm"]{border:1px solid #e4e9df;border-radius:19px;padding:1rem;background:#fffefa}
[data-baseweb="input"],[data-baseweb="select"]>div,textarea{border-radius:10px!important}
.hero{background:#dfefe6;border:1px solid #cfdfd3;border-radius:22px;padding:21px 23px;margin-bottom:6px}
.eyebrow{font-size:12px;font-weight:700;letter-spacing:1px;color:#507363;margin-bottom:7px}
.hero-title{font-size:23px;font-weight:750;letter-spacing:-.6px;margin-bottom:6px}
.hero-note{font-size:14px;color:#4e675c;line-height:1.6}
.stat{padding:15px;border-radius:17px;background:#ece6f5;min-height:105px}
.stat.mint{background:#dfefe6}.stat.peach{background:#f8e5d9}
.stat-label{font-size:13px;font-weight:600}.stat-number{font-size:29px;font-weight:750;margin-top:5px}
.note{background:#fffefa;border:1px solid #e6e8dd;border-radius:16px;padding:14px 16px;margin:5px 0 10px}
.note-title{font-size:15px;font-weight:700;overflow-wrap:anywhere}
.note-body{font-size:14px;line-height:1.65;white-space:pre-wrap;overflow-wrap:anywhere;margin-top:6px}
.note-meta{font-size:12px;color:#617169;margin-top:5px}
[data-testid="stCaptionContainer"]{color:#65766d}
@media(max-width:600px){.block-container{padding:.8rem .7rem!important}h1{font-size:1.4rem!important}.hero{padding:15px}.hero-title{font-size:20px}.stat{padding:10px;min-height:90px}.stat-number{font-size:24px}}
</style>''', unsafe_allow_html=True)

st.title('🌷 선생님의 작은 교무실')
st.caption('수업의 이어짐도, 업무의 마무리도. 한곳에서 차근차근.')
if not teachers:
    st.info('먼저 Settings → Secrets에 teachers 계정을 등록해주세요. Python 파일 맨 위에 설정 예시와 저장소 SQL이 있습니다.')
    st.stop()
if any(not dict(t).get('password') for t in teachers.values()):
    st.error('모든 교사 계정에 개인 비밀번호를 설정해주세요.'); st.stop()
passwords = [str(dict(t)['password']) for t in teachers.values()]
if len(passwords) != len(set(passwords)):
    st.error('계정별 비밀번호를 서로 다르게 설정해주세요.'); st.stop()
if bool(sb.get('url')) != bool(sb.get('service_role_key')):
    st.error('Supabase url과 service_role_key를 모두 설정해주세요.'); st.stop()

if 'owner' not in st.session_state:
    with st.form('login'):
        account = st.selectbox('사용자', list(teachers), format_func=lambda x: str(dict(teachers[x]).get('name', x)))
        password = st.text_input('개인 비밀번호', type='password')
        enter = st.form_submit_button('내 교무실 들어가기 →', use_container_width=True, type='primary')
    if enter:
        now = time.time()
        if now < st.session_state.get('retry_after', 0):
            st.error('잠시 후 다시 시도해주세요.')
        elif hmac.compare_digest(password.encode(), str(dict(teachers[account])['password']).encode()):
            st.session_state.owner = account
            st.session_state.auth_digest = hashlib.sha256(str(dict(teachers[account])['password']).encode()).hexdigest()
            st.rerun()
        else:
            n = st.session_state.get('failures', 0) + 1
            st.session_state.failures = n
            st.session_state.retry_after = now + min(60, 2 ** min(6, n))
            st.error('비밀번호를 확인해주세요.')
    st.caption('개인 계정으로 기록을 구분합니다. 학생 개인정보는 입력하지 마세요.')
    st.stop()

owner = st.session_state.owner
if owner not in teachers or not hmac.compare_digest(st.session_state.get('auth_digest', ''), hashlib.sha256(str(dict(teachers[owner])['password']).encode()).hexdigest()):
    st.session_state.clear(); st.rerun()
profile = dict(teachers[owner])
name = str(profile.get('name', owner))

def choices(key, default):
    raw = profile.get(key, default)
    if not isinstance(raw, list): return default
    result = list(dict.fromkeys(str(x).strip() for x in raw if str(x).strip()))
    return result or default

classes = choices('classes', ['우리 반'])
subjects = choices('subjects', ['담당 과목'])

def db():
    con = sqlite3.connect(str(Path(__file__).with_name('teacher_demo.sqlite3')), timeout=20)
    con.row_factory = sqlite3.Row
    con.execute('CREATE TABLE IF NOT EXISTS teacher_records(id TEXT PRIMARY KEY,owner TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,version INTEGER NOT NULL,created_at TEXT NOT NULL)')
    return con

def api(method, params=None, payload=None):
    key = str(sb['service_role_key'])
    r = requests.request(method, str(sb['url']).rstrip('/') + '/rest/v1/teacher_records',
        params=params, json=payload, timeout=20,
        headers={'apikey': key, 'Authorization': f'Bearer {key}', 'Prefer': 'return=representation'})
    r.raise_for_status()
    return r.json() if r.content else []

def load_records():
    if remote:
        result, offset = [], 0
        while True:
            page = api('GET', {'select': '*', 'owner': f'eq.{owner}', 'order': 'created_at.asc,id.asc', 'limit':'1000', 'offset':str(offset)})
            if not page: break
            result.extend(page); offset += len(page)
        return result
    with db() as con:
        rows = [dict(r) for r in con.execute('SELECT * FROM teacher_records WHERE owner=? ORDER BY created_at,id', (owner,))]
    for r in rows: r['payload'] = json.loads(r['payload'])
    return rows

class Conflict(Exception):
    pass

def create_record(kind, payload, record_id):
    row = dict(id=record_id,owner=owner,kind=kind,payload=payload,version=1,created_at=datetime.now(timezone.utc).isoformat())
    if remote:
        try:
            api('POST', payload=row)
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 409: raise
            # 재시도 UUID 충돌은 내 계정의 동일 요청에 한해 성공 처리.
            existing = api('GET', {'id':f'eq.{record_id}', 'owner':f'eq.{owner}', 'select':'id'})
            if not existing: raise
    else:
        with db() as con:
            con.execute('INSERT OR IGNORE INTO teacher_records VALUES (?,?,?,?,?,?)',
                (record_id,owner,kind,json.dumps(payload,ensure_ascii=False),1,row['created_at']))

def update_record(row, payload):
    if remote:
        changed = api('PATCH', {'id':f"eq.{row['id']}", 'owner':f'eq.{owner}', 'version':f"eq.{row['version']}"},
                      {'payload':payload,'version':row['version']+1})
        if not changed: raise Conflict()
    else:
        with db() as con:
            cursor = con.execute('UPDATE teacher_records SET payload=?,version=version+1 WHERE id=? AND owner=? AND version=?',
                (json.dumps(payload,ensure_ascii=False),row['id'],owner,row['version']))
            if cursor.rowcount != 1: raise Conflict()

def delete_record(row):
    if remote:
        changed = api('DELETE', {'id':f"eq.{row['id']}", 'owner':f'eq.{owner}', 'version':f"eq.{row['version']}"})
        if not changed: raise Conflict()
    else:
        with db() as con:
            cursor = con.execute('DELETE FROM teacher_records WHERE id=? AND owner=? AND version=?', (row['id'],owner,row['version']))
            if cursor.rowcount != 1: raise Conflict()

def mutate(function, *args):
    try:
        function(*args)
    except Conflict:
        st.warning('다른 창에서 기록이 변경되었거나 삭제됐어요. ↻로 최신 내용을 확인한 후 다시 시도해주세요.')
        return False
    except (requests.RequestException, sqlite3.Error):
        st.error('변경 결과를 확인하지 못했어요. ↻로 기록을 확인한 후 다시 시도해주세요.')
        return False
    return True

def task_due(row):
    return date.fromisoformat(row['payload']['due'])

def open_tasks(rows):
    return sorted([r for r in rows if r['kind']=='task' and not r['payload'].get('done')],
                  key=lambda r: (task_due(r), 0 if r['payload'].get('priority')=='중요' else 1, r['id']))

def latest_lessons(rows):
    result = {}
    for r in rows:
        if r['kind']!='lesson': continue
        p = r['payload']; key = (p['class'],p['subject'])
        candidate = (p['date'],r['created_at'],r['id'])
        if key not in result:
            result[key]=r
        else:
            old=result[key]
            if candidate > (old['payload']['date'],old['created_at'],old['id']): result[key]=r
    return [result[k] for k in sorted(result)]

def next_year(value):
    d=date.fromisoformat(value); year=d.year+1
    return d.replace(year=year, day=min(d.day,calendar.monthrange(year,d.month)[1]))

def e(value): return html.escape(str(value))

def card(title, body='', meta=''):
    st.markdown(f'<div class="note"><div class="note-title">{e(title)}</div><div class="note-body">{e(body)}</div><div class="note-meta">{e(meta)}</div></div>', unsafe_allow_html=True)

def lesson_card(row):
    p=row['payload']
    card(f"📖 {p['class']} · {p['subject']}",
         f"{p['topic']}" + (f" · {p['pages']}" if p.get('pages') else '') + '\n다음 시간: ' + (p.get('next') or '메모 없음'),
         f"{p['date']}" + (f" · 과제: {p['homework']}" if p.get('homework') else ''))

def task_title(row):
    p=row['payload']; delta=(task_due(row)-TODAY).days
    badge = '완료' if p.get('done') else (f'{abs(delta)}일 지남' if delta<0 else ('오늘 마감' if delta==0 else f'D−{delta}'))
    return f"{'★ ' if p.get('priority')=='중요' else ''}{p['title']} · {badge}"

bar1,bar2,bar3 = st.columns([6,1,1])
bar1.caption(f"{name}의 기록 · {'클라우드 저장' if remote else '⚠️ 임시 체험 저장'} · {TODAY:%Y.%m.%d}")
if bar2.button('↻',help='최신 기록 새로고침',use_container_width=True): st.rerun()
with bar3.popover('⚙️',use_container_width=True):
    st.caption('주소 공유 · 개인 계정으로 로그인해야 기록이 보입니다.')
    url=str(app.get('url','')).strip()
    if url.startswith('https://'):
        buf=io.BytesIO(); qrcode.make(url).save(buf,format='PNG')
        st.image(buf.getvalue(),width=170)
        st.link_button('접속 주소 열기',url)
    else: st.caption('app.url에 배포 주소를 넣으면 QR을 표시합니다.')
    st.caption('수업 반·과목·사용자 이름은 Secrets에서 변경하세요. 계정 ID는 변경하지 마세요.')
    if not remote: st.warning('체험 기록은 재시작 시 사라질 수 있습니다. 실제 사용은 Supabase를 연결하세요.')
    if st.button('로그아웃',use_container_width=True): st.session_state.clear(); st.rerun()

try:
    rows=load_records()
    tasks=open_tasks(rows)
    lessons=latest_lessons(rows)
except (requests.RequestException,sqlite3.Error,ValueError,KeyError,TypeError):
    st.error('기록을 불러오지 못했어요. 저장소 설정을 확인한 후 ↻를 눌러주세요.'); st.stop()

page=st.segmented_control('메뉴',['🏡 메인','📖 수업 진도','🗓️ 업무 일정'],default='🏡 메인',label_visibility='collapsed',key='page')
if not page: page='🏡 메인'

# 실패한 신규 저장은 입력 폼과 별도로 원문/UUID를 보관합니다.
pending=st.session_state.get('pending_record')
if pending:
    st.warning('결과가 확인되지 않은 저장 요청이 있어요. 재시도해도 같은 요청은 중복 저장되지 않습니다.')
    with st.expander('미확정 원문과 재시도'):
        st.json(pending['payload'])
        if st.button('이 요청 그대로 재시도'):
            if mutate(create_record,pending['kind'],pending['payload'],pending['id']):
                st.session_state.pop('pending_record',None); st.rerun()

def submit_new(kind,payload,record_id):
    if st.session_state.get('pending_record'):
        st.warning('미확정 요청을 먼저 재시도해주세요.'); return
    st.session_state.pending_record={'kind':kind,'payload':payload,'id':record_id}
    if mutate(create_record,kind,payload,record_id):
        st.session_state.pop('pending_record',None)
        st.session_state.pop('draft_'+kind,None)
        st.rerun()

if page=='🏡 메인':
    overdue=[r for r in tasks if task_due(r)<TODAY]
    today=[r for r in tasks if task_due(r)==TODAY]
    week=[r for r in tasks if TODAY<=task_due(r)<=TODAY+timedelta(days=6)]
    note='오늘 마감 업무가 없어요. 수업 준비를 차분하게 시작해볼까요?' if not today else f'오늘 마감 업무 {len(today)}개가 기다리고 있어요. 하나씩 함께 마무리해요.'
    st.markdown(f'<div class="hero"><div class="eyebrow">MY LITTLE TEACHER DESK</div><div class="hero-title">{e(name)}, 오늘도 반가워요 🌱</div><div class="hero-note">{e(note)}</div></div>',unsafe_allow_html=True)
    for col,label,value,tone in zip(st.columns(3),['오늘 마감','기한 지난 업무','오늘부터 7일'],[len(today),len(overdue),len(week)],['mint','peach','']):
        col.markdown(f'<div class="stat {tone}"><div class="stat-label">{label}</div><div class="stat-number">{value}<span style="font-size:13px"> 개</span></div></div>',unsafe_allow_html=True)
    st.subheader('📝 먼저 챙길 일')
    if not tasks: st.info('등록된 미완료 업무가 없어요. 업무 일정에서 할 일을 추가해보세요.')
    for r in tasks[:5]:
        p=r['payload']; left,right=st.columns([6,1])
        with left: card(task_title(r),p.get('notes',''),f"{p['due']} · {p.get('category','기타')}")
        if right.button('완료',key='home_done_'+r['id'],help='완료 처리'):
            if mutate(update_record,r,{**p,'done':True}): st.rerun()
    if len(tasks)>5: st.caption(f'나머지 {len(tasks)-5}개는 업무 일정에서 확인하세요.')
    st.subheader('📚 반별 마지막 수업')
    st.caption('등록된 기록의 수업 날짜 기준입니다. 오늘 시간표나 실제 수업 여부를 추정하지 않습니다.')
    if not lessons: st.info('수업 진도에서 첫 수업 기록을 남겨보세요.')
    for r in lessons: lesson_card(r)

elif page=='📖 수업 진도':
    st.subheader('📖 오늘의 수업 한 장')
    st.caption('반·과목별 진도와 다음 시간 메모를 이어서 관리해요.')
    mode=st.radio('수업 화면',['새 기록','기록 찾기 · 수정','반별 진도 비교'],horizontal=True,label_visibility='collapsed')
    if mode=='새 기록':
        st.session_state.setdefault('draft_lesson',str(uuid.uuid4()))
        with st.form('new_lesson_'+st.session_state.draft_lesson,clear_on_submit=False):
            c1,c2,c3=st.columns(3)
            class_name=c1.selectbox('학년 · 반',classes)
            subject=c2.selectbox('과목',subjects)
            when=c3.date_input('수업 날짜',TODAY)
            topic=st.text_input('단원 · 수업 내용 *',max_chars=150,placeholder='예: 3단원 설명하는 글 읽기')
            pages=st.text_input('교과서 쪽수',max_chars=50,placeholder='예: 42~45쪽')
            next_note=st.text_area('다음 시간에 할 일',max_chars=1000,height=90,placeholder='예: 46쪽 활동 2부터 시작하기')
            homework=st.text_input('과제',max_chars=250)
            notes=st.text_area('수업 메모',max_chars=2000,height=90,placeholder='수업 운영 메모만 기록해주세요. 학생 개인정보 입력 금지')
            submit=st.form_submit_button('수업 기록 남기기',type='primary',use_container_width=True)
        if submit:
            if not topic.strip(): st.warning('단원·수업 내용을 입력해주세요.')
            else: submit_new('lesson',{'class':class_name,'subject':subject,'date':when.isoformat(),'topic':topic.strip(),'pages':pages.strip(),'next':next_note.strip(),'homework':homework.strip(),'notes':notes.strip()},st.session_state.draft_lesson)
    elif mode=='반별 진도 비교':
        for r in lessons: lesson_card(r)
        if not lessons: st.info('아직 수업 기록이 없어요.')
    else:
        all_lessons=[r for r in rows if r['kind']=='lesson']
        known_classes=list(dict.fromkeys(classes+[r['payload']['class'] for r in all_lessons]))
        f1,f2=st.columns(2)
        selected_class=f1.selectbox('반 필터',['전체']+known_classes)
        query=f2.text_input('단원 · 메모 검색',max_chars=100)
        matched=sorted([r for r in all_lessons if (selected_class=='전체' or r['payload']['class']==selected_class) and query.casefold() in json.dumps(r['payload'],ensure_ascii=False).casefold()],key=lambda r:(r['payload']['date'],r['created_at'],r['id']),reverse=True)
        if not matched: st.info('조건에 맞는 수업 기록이 없어요.')
        else:
            lookup={r['id']:r for r in matched}
            selected=st.selectbox('기록 선택',list(lookup),format_func=lambda k:f"{lookup[k]['payload']['date']} · {lookup[k]['payload']['class']} · {lookup[k]['payload']['subject']} · {lookup[k]['payload']['topic']}")
            r=lookup[selected]; p=r['payload']
            with st.form('edit_lesson_'+r['id']+'_'+str(r['version'])):
                st.caption(f"{p['class']} · {p['subject']} (반·과목이 잘못되었다면 삭제 후 다시 등록)")
                when=st.date_input('수업 날짜',date.fromisoformat(p['date']))
                topic=st.text_input('단원 · 수업 내용',p['topic'],max_chars=150)
                pages=st.text_input('교과서 쪽수',p.get('pages',''),max_chars=50)
                next_note=st.text_area('다음 시간',p.get('next',''),max_chars=1000,height=90)
                homework=st.text_input('과제',p.get('homework',''),max_chars=250)
                notes=st.text_area('수업 메모',p.get('notes',''),max_chars=2000,height=90)
                update=st.form_submit_button('수정 저장',use_container_width=True)
            if update:
                if not topic.strip(): st.warning('수업 내용을 입력해주세요.')
                elif mutate(update_record,r,{**p,'date':when.isoformat(),'topic':topic.strip(),'pages':pages.strip(),'next':next_note.strip(),'homework':homework.strip(),'notes':notes.strip()}): st.rerun()
            with st.popover('이 기록 삭제'):
                confirm=st.checkbox('선택한 기록을 영구 삭제합니다',key='confirm_'+r['id'])
                if st.button('영구 삭제',disabled=not confirm,key='delete_'+r['id']):
                    if mutate(delete_record,r): st.rerun()

else:
    st.subheader('🗓️ 업무도 한 칸씩 가볍게')
    st.caption('마감일·중요도·체크리스트를 관리하고, 지난 업무를 다음 해에 복사해요.')
    with st.expander('＋ 새 업무 등록',expanded=not any(r['kind']=='task' for r in rows)):
        st.session_state.setdefault('draft_task',str(uuid.uuid4()))
        with st.form('new_task_'+st.session_state.draft_task):
            title=st.text_input('업무 이름 *',max_chars=120,placeholder='예: 현장체험학습 준비')
            c1,c2,c3=st.columns(3)
            due=c1.date_input('마감일',TODAY)
            priority=c2.selectbox('중요도',['보통','중요'])
            category=c3.selectbox('분류',['수업','행정','행사','제출','기타'])
            steps=st.text_area('세부 할 일 · 한 줄에 하나',max_chars=2000,height=90,placeholder='일정 확인\n준비물 점검\n안내 문구 작성')
            notes=st.text_area('메모',max_chars=2000,height=90)
            link=st.text_input('관련 링크 (https://)',max_chars=1000)
            submit=st.form_submit_button('업무 추가',type='primary',use_container_width=True)
        if submit:
            if not title.strip(): st.warning('업무 이름을 입력해주세요.')
            elif link.strip() and not link.strip().startswith('https://'): st.warning('관련 링크는 https://로 시작해야 합니다.')
            else:
                payload={'title':title.strip(),'due':due.isoformat(),'priority':priority,'category':category,'notes':notes.strip(),'link':link.strip(),'done':False,'steps':[{'text':s.strip(),'done':False} for s in steps.splitlines() if s.strip()]}
                submit_new('task',payload,st.session_state.draft_task)
    f1,f2=st.columns(2)
    status=f1.selectbox('업무 필터',['미완료 전체','오늘 마감','7일 이내','기한 지남','완료','전체'])
    query=f2.text_input('업무 검색',max_chars=100)
    def include(r):
        p=r['payload']; done=p.get('done',False); due=task_due(r)
        return ((status=='전체') or (status=='완료' and done) or (not done and (status=='미완료 전체' or (status=='오늘 마감' and due==TODAY) or (status=='7일 이내' and TODAY<=due<=TODAY+timedelta(days=6)) or (status=='기한 지남' and due<TODAY)))) and query.casefold() in json.dumps(p,ensure_ascii=False).casefold()
    matched=sorted([r for r in rows if r['kind']=='task' and include(r)],key=lambda r:(r['payload'].get('done',False),task_due(r),r['id']))
    if not matched: st.info('조건에 맞는 업무가 없어요 🌱')
    for r in matched:
        p=r['payload']; unique=r['id']+'_'+str(r['version'])
        with st.expander(('✅ ' if p.get('done') else '🗒️ ')+task_title(r)):
            st.caption(f"{p['due']} · {p['category']} · {p['priority']}")
            if p.get('notes'): st.text(p['notes'])
            if p.get('link','').startswith('https://'): st.link_button('관련 자료 열기',p['link'])
            new_steps=[]
            for i,s in enumerate(p.get('steps',[])):
                checked=st.checkbox(s['text'],value=bool(s.get('done')),key=f'step_{unique}_{i}')
                new_steps.append({'text':s['text'],'done':checked})
            if new_steps and st.button('체크리스트 저장',key='steps_'+unique):
                if mutate(update_record,r,{**p,'steps':new_steps}): st.rerun()
            c1,c2=st.columns(2)
            if c1.button('미완료로 되돌리기' if p.get('done') else '업무 완료 ✓',key='toggle_'+unique,use_container_width=True):
                # 체크박스 변경분도 함께 저장합니다.
                if mutate(update_record,r,{**p,'done':not p.get('done',False),'steps':new_steps}): st.rerun()
            if c2.button('다음 해 업무로 복사',key='copy_'+unique,use_container_width=True):
                copy_id=str(uuid.uuid5(uuid.NAMESPACE_URL,owner+':next-year:'+r['id']))
                copied={**p,'due':next_year(p['due']).isoformat(),'done':False,'steps':[{'text':s['text'],'done':False} for s in p.get('steps',[])]}
                submit_new('task',copied,copy_id)
            with st.form('edit_task_'+unique):
                title=st.text_input('업무 이름',p['title'],max_chars=120)
                due=st.date_input('마감일 변경',task_due(r))
                priority=st.selectbox('중요도',['보통','중요'],index=1 if p.get('priority')=='중요' else 0)
                notes=st.text_area('업무 메모',p.get('notes',''),max_chars=2000,height=90)
                link=st.text_input('관련 링크',p.get('link',''),max_chars=1000)
                steps_text=st.text_area('세부 할 일 편집 · 한 줄에 하나',value='\n'.join(s['text'] for s in p.get('steps',[])),max_chars=2000,height=90)
                save_edit=st.form_submit_button('업무 수정 저장')
            if save_edit:
                if not title.strip(): st.warning('업무 이름을 입력해주세요.')
                elif link.strip() and not link.strip().startswith('https://'): st.warning('https:// 링크만 등록해주세요.')
                else:
                    # 동일 문구의 체크 상태를 순서대로 보존하고 새 문구만 미완료로 추가.
                    old={}
                    for s in new_steps: old.setdefault(s['text'],[]).append(s['done'])
                    edited=[]
                    for line in steps_text.splitlines():
                        text=line.strip()
                        if text: edited.append({'text':text,'done':old[text].pop(0) if old.get(text) else False})
                    if mutate(update_record,r,{**p,'title':title.strip(),'due':due.isoformat(),'priority':priority,'notes':notes.strip(),'link':link.strip(),'steps':edited}): st.rerun()
            with st.popover('업무 삭제'):
                confirm=st.checkbox('영구 삭제 확인',key='confirm_'+unique)
                if st.button('삭제',disabled=not confirm,key='delete_'+unique):
                    if mutate(delete_record,r): st.rerun()

# 모든 화면에서 내 계정 자료만 내려받습니다.
def csv_bytes(kind):
    out=io.StringIO(); w=csv.writer(out)
    def safe(value):
        text=str(value)
        return "'"+text if text.lstrip().startswith(('=','+','-','@')) else text
    if kind=='lesson':
        w.writerow(['날짜','반','과목','단원','쪽수','다음 시간','과제','메모'])
        keys=['date','class','subject','topic','pages','next','homework','notes']
        for r in rows:
            if r['kind']==kind: w.writerow([safe(r['payload'].get(k,'')) for k in keys])
    else:
        w.writerow(['마감일','업무','분류','중요도','완료','메모','관련 링크','체크리스트'])
        for r in rows:
            if r['kind']==kind:
                p=r['payload']; w.writerow([safe(p['due']),safe(p['title']),safe(p['category']),safe(p['priority']),'완료' if p.get('done') else '미완료',safe(p.get('notes','')),safe(p.get('link','')),safe('\n'.join(('☑ ' if s['done'] else '☐ ')+s['text'] for s in p.get('steps',[])))])
    return out.getvalue().encode('utf-8-sig')

def ics_escape(value):
    return str(value).replace('\\','\\\\').replace('\r\n','\n').replace('\r','\n').replace('\n','\\n').replace(';','\\;').replace(',','\\,')

def ics_bytes(task_rows):
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Little Teacher Desk//KO','CALSCALE:GREGORIAN']
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for r in task_rows:
        p=r['payload']; due=task_due(r)
        lines+=['BEGIN:VEVENT',f"UID:{r['id']}@little-teacher-desk",f'DTSTAMP:{stamp}',f'DTSTART;VALUE=DATE:{due:%Y%m%d}',f'DTEND;VALUE=DATE:{due+timedelta(days=1):%Y%m%d}',
                'SUMMARY:'+ics_escape('[마감] '+p['title']),'DESCRIPTION:'+ics_escape(p.get('notes','')),'TRANSP:TRANSPARENT','END:VEVENT']
    lines+=['END:VCALENDAR']
    # iCalendar의 UTF-8 75바이트 줄 접기(연속 줄은 공백 1바이트).
    folded=[]
    for line in lines:
        current=''
        for char in line:
            if len((current+char).encode('utf-8'))>75:
                folded.append(current); current=' '+char
            else: current+=char
        folded.append(current)
    return ('\r\n'.join(folded)+'\r\n').encode('utf-8')

st.divider()
with st.expander('📦 내 기록 내보내기 · 사용 안내'):
    a,b=st.columns(2)
    a.download_button('수업 기록 CSV',csv_bytes('lesson'),'lessons.csv','text/csv',use_container_width=True)
    b.download_button('업무 기록 CSV',csv_bytes('task'),'tasks.csv','text/csv',use_container_width=True)
    st.download_button('미완료 업무를 캘린더로 (.ics)',ics_bytes(tasks),'teacher_deadlines.ics','text/calendar',use_container_width=True)
    st.caption('캘린더 파일은 마감일의 종일 일정입니다. 다운로드 후 사용하는 캘린더에 직접 가져오세요. 자동 연동·알림·수정 반영은 하지 않습니다. 반복 가져오기는 캘린더에 따라 중복될 수 있습니다.')
    st.download_button('전체 원본 JSON 백업',json.dumps(rows,ensure_ascii=False,indent=2).encode('utf-8'),'teacher_backup.json','application/json',use_container_width=True)
    st.caption('CSV/JSON은 내보내기 전용이며 앱 내 가져오기는 지원하지 않습니다. 다음 해 복사는 원본 업무당 한 번 생성됩니다. 기록은 ↻를 눌러 갱신하세요. 학생 개인정보나 학교 내부 비밀자료는 입력하지 마세요.')
