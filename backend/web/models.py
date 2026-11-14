"""Model profiles, encrypted credential versions, and explicit outbound endpoints."""
import ipaddress, os, socket, stat, uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from cryptography.fernet import Fernet, InvalidToken
from db import one, rows

PRESETS = [
    {'provider':'DeepSeek','base_url':'https://api.deepseek.com','model':'deepseek-flash'},
    {'provider':'通义千问','base_url':'https://dashscope.aliyuncs.com/compatible-mode/v1','model':''},
    {'provider':'智谱 GLM','base_url':'https://open.bigmodel.cn/api/paas/v4','model':''},
    {'provider':'Kimi','base_url':'https://api.moonshot.cn/v1','model':''},
    {'provider':'自定义兼容接口','base_url':'','model':''},
]

def normalize_url(value, resolve=False):
    value=value.strip().rstrip('/')
    try:
        u=urlsplit(value)
        port=u.port
        if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment or port not in (None,443):raise ValueError()
        if any(c.isspace() for c in value) or '%' in u.netloc or '\\' in value:raise ValueError()
        host=u.hostname.encode('idna').decode('ascii').lower()
        if ':' in host:raise ValueError()
        if host=='localhost' or host.endswith(('.localhost','.local','.internal')):raise ValueError()
        try:
            if not ipaddress.ip_address(host).is_global:raise ValueError('非公网地址')
        except ValueError as error:
            if str(error)=='非公网地址':raise
            if ':' in host or all(c in '0123456789.' for c in host):raise ValueError()
        if u.path.endswith('/chat/completions'):raise ValueError()
        if any(part in ('.','..') for part in u.path.split('/')):raise ValueError()
        url=urlunsplit(('https',host,u.path.rstrip('/'),'',''))
    except (ValueError,UnicodeError):raise ValueError('Base URL须为公网HTTPS接口根地址（不含Key、查询参数或/chat/completions）')
    if resolve:
        try:addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        except OSError:raise ValueError('模型接口域名无法解析，请检查Base URL')
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('模型接口必须解析到公网地址')
    return url

def cipher():
    configured=os.getenv('KNOWLEDGE_ENCRYPTION_KEY')
    if configured:
        try:return Fernet(configured.encode())
        except ValueError:raise ValueError('服务端加密主密钥格式错误')
    path=Path(os.getenv('KNOWLEDGE_MASTER_KEY_FILE',str(Path(__file__).resolve().parents[1]/'runtime/master.key')))
    if not path.exists():
        # Never silently replace a lost key: doing so strands existing credentials.
        if one('SELECT id FROM model_credentials LIMIT 1'):raise ValueError('加密主密钥缺失，请恢复原主密钥；现有模型Key未被覆盖')
        path.parent.mkdir(parents=True,exist_ok=True)
        try:
            fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError:pass
        else:
            with os.fdopen(fd,'wb') as f:f.write(Fernet.generate_key())
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode)&0o077:raise ValueError('加密主密钥文件权限须为600，且不能为符号链接')
    try:return Fernet(path.read_bytes().strip())
    except ValueError:raise ValueError('加密主密钥损坏，请恢复备份')

def add_credential(cur,model_id,base_url,key):
    key=key.strip()
    if not 8<=len(key)<=4096 or any(c.isspace() for c in key):raise ValueError('Key格式不正确，请重新填写')
    token=cipher().encrypt(key.encode()).decode();cid=uuid.uuid4().hex
    cur.execute('INSERT INTO model_credentials(id,model_id,base_url,ciphertext) VALUES(%s,%s,%s,%s)',(cid,model_id,base_url,token))
    return cid

def has_key(profile):
    return bool(profile.get('credential_id') or (profile.get('env_key') and os.getenv('DEEPSEEK_API_KEY')))

def public_profile(profile):
    return {**{k:v for k,v in profile.items() if k not in ['credential_id','env_key']},'key_configured':has_key(profile),'key_display':'已配置 · 不回显' if has_key(profile) else '未配置'}

def profiles():return [public_profile(r) for r in rows('SELECT * FROM model_profiles ORDER BY created_at,id')]

def snapshot(profile):
    return {k:(float(v) if k in ['input_price','output_price'] and v is not None else v) for k,v in profile.items() if k in ['id','name','provider','base_url','model','json_mode','version','credential_id','env_key','input_price','output_price','currency']}

def resolve_key(profile):
    cid=profile.get('credential_id')
    if cid:
        credential=one('SELECT * FROM model_credentials WHERE id=%s',(cid,))
        if not credential or credential['model_id']!=profile['id'] or credential['base_url']!=profile['base_url']:raise ValueError('模型凭据与接口不匹配，请重新配置')
        try:return cipher().decrypt(credential['ciphertext'].encode()).decode()
        except InvalidToken:raise ValueError('模型Key解密失败，请恢复原主密钥')
    if profile.get('env_key') and profile['base_url']=='https://api.deepseek.com':
        key=os.getenv('DEEPSEEK_API_KEY')
        if key:return key
    raise ValueError('所选模型未配置Key，请在模型管理中添加')
