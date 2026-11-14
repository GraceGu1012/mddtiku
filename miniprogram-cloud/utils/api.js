// 微信云托管版 API：请求经微信内部通道（wx.cloud.callContainer），免域名、免备案、不受 IP 拦截影响。
// 部署云托管服务后，把 CLOUD_ENV 改成云托管环境 ID 即可。
const CLOUD_ENV = 'prod-d1g3ohbkt443313be'; // 微信云托管环境 ID
const SERVICE_NAME = 'mdd-learner-api';

let boot = null;
let bootPromise = null;
let cookie = '';

wx.cloud.init({ env: CLOUD_ENV });

function rawRequest(method, path, body) {
    return new Promise((resolve, reject) => {
        const header = {};
        // 服务名必须走 X-WX-SERVICE 请求头（callContainer 官方写法），
        // 网关靠它路由到具体服务，缺失会报 -601031 INVALID_PATH。
        header['X-WX-SERVICE'] = SERVICE_NAME;
        if (cookie) {
            header.Cookie = cookie;
        }
        if (body !== undefined) {
            header['Content-Type'] = 'application/json';
            if (boot && boot.csrf) {
                header['X-CSRF-Token'] = boot.csrf;
            }
        }
        wx.cloud.callContainer({
            config: { env: CLOUD_ENV },
            path: path,
            method: method,
            serviceName: SERVICE_NAME,
            data: body === undefined ? {} : body,
            header: header,
            success(res) {
                const headers = res.header || {};
                const setCookie = headers['set-cookie'] || headers['Set-Cookie'];
                if (setCookie) {
                    const raw = Array.isArray(setCookie) ? setCookie.join(';') : String(setCookie);
                    const match = raw.match(/mdd_learner=[^;,\s]+/);
                    if (match) {
                        cookie = match[0];
                    }
                }
                if (res.statusCode >= 200 && res.statusCode < 300) {
                    resolve(res.data);
                    return;
                }
                const detail = res.data && typeof res.data.detail === 'string' ? res.data.detail : '';
                const error = new Error(detail || '请求未完成，请稍后重试');
                error.statusCode = res.statusCode;
                reject(error);
            },
            fail(err) {
                const raw = err && err.errMsg ? String(err.errMsg) : '';
                let text = '云托管通道连接失败，请稍后重试';
                if (/env|checkEnv|ENV/i.test(raw)) {
                    text = '云托管环境未开通或环境 ID 未配置';
                } else if (/container|service|not found|404/i.test(raw)) {
                    text = '云托管服务不存在或未启动';
                } else if (/timeout/i.test(raw)) {
                    text = '连接服务器超时，请稍后重试';
                }
                const error = new Error(raw ? text + '（' + raw + '）' : text);
                error.statusCode = 0;
                error.rawMessage = raw;
                reject(error);
            },
        });
    });
}

function ensureBoot(force) {
    if (boot && !force) {
        return Promise.resolve(boot);
    }
    if (bootPromise && !force) {
        return bootPromise;
    }
    bootPromise = rawRequest('GET', '/api/learn/bootstrap')
        .then((data) => {
            boot = data;
            bootPromise = null;
            return boot;
        })
        .catch((err) => {
            bootPromise = null;
            throw err;
        });
    return bootPromise;
}

function api(path, body) {
    const method = body === undefined ? 'GET' : 'POST';
    return ensureBoot()
        .then(() => rawRequest(method, '/api/learn/' + path, body))
        .catch((err) => {
            if (err && err.statusCode === 401) {
                boot = null;
                cookie = '';
                return ensureBoot(true).then(() => rawRequest(method, '/api/learn/' + path, body));
            }
            throw err;
        });
}

function getBoot() {
    return boot;
}

module.exports = {
    api: api,
    ensureBoot: ensureBoot,
    getBoot: getBoot,
};
