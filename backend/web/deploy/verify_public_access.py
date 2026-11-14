"""Verify the explicitly requested public entry without credentials or business writes."""
import json,ssl,sys,urllib.request,urllib.error
base=sys.argv[1].rstrip('/')
context=ssl.create_default_context(cafile=sys.argv[2])
result={}
for path in ['/', '/learn', '/api/bootstrap', '/api/items?library=true']:
    with urllib.request.urlopen(base+path,context=context,timeout=20) as response:
        assert response.status==200
        assert response.headers.get('WWW-Authenticate') is None
        result[path]=response.status
request=urllib.request.Request(base+'/api/settings',data=b'{}',headers={'Content-Type':'application/json','Origin':base},method='POST')
try:
    urllib.request.urlopen(request,context=context,timeout=20)
    raise AssertionError('Missing CSRF protection')
except urllib.error.HTTPError as error:
    assert error.code==403
    result['missing_csrf_rejected']=True
print(json.dumps(result,ensure_ascii=False,indent=2))
