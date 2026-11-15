// 强制 Node 出口走 IPv4：dns.lookup 钉 family=4 + net.connect 默认 family=4
// 用途：miniprogram-ci 上传时本机 IPv6 不在微信白名单（-10008）
const dns = require('node:dns');
const net = require('node:net');
const wrap = (orig) => function (hostname, options, callback) {
  if (typeof options === 'function') { callback = options; options = {}; }
  if (typeof options === 'number') options = { family: options };
  options = Object.assign({}, options, { family: 4 });
  return orig.call(this, hostname, options, callback);
};
dns.lookup = wrap(dns.lookup);
if (dns.promises && dns.promises.lookup) dns.promises.lookup = wrap(dns.promises.lookup);
const _connect = net.connect;
net.connect = function (...args) {
  const opts = typeof args[0] === 'object' && args[0] ? args[0] : null;
  if (opts && !opts.family && !opts.path) opts.family = 4;
  return _connect.apply(this, args);
};
