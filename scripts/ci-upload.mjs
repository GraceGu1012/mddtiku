// 云托管版小程序上传（生成开发版本，供微信公众平台提交审核）
// 用法: node scripts/ci-upload.mjs <版本号> [备注]
// 注意：首行剥离 NODE_OPTIONS，规避会话 shim 导致的 fork spawn ENOENT。
delete process.env.NODE_OPTIONS
// ci 会 fork 子进程执行上传：注入 force-ipv4 补丁（本机 IPv6 不在微信白名单，-10008）
// 注意：还需用 env -i 白名单环境运行本脚本，绕开沙箱 HTTP(S)_PROXY（代理出口也是 IPv6）
process.env.NODE_OPTIONS = '--require ' + import.meta.dirname + '/force-ipv4.cjs'

async function main() {
  const { default: ci } = await import('miniprogram-ci')
  const path = await import('node:path')
  const { fileURLToPath } = await import('node:url')

  const [version, desc] = process.argv.slice(2)
  if (!version) {
    console.error('用法: node scripts/ci-upload.mjs <版本号> [备注]')
    process.exit(1)
  }

  const scriptDir = path.dirname(fileURLToPath(import.meta.url))
  const root = path.resolve(scriptDir, '..')
  const project = new ci.Project({
    appid: 'wxc76296654f49320a',
    type: 'miniProgram',
    projectPath: path.join(root, 'miniprogram-cloud'),
    privateKeyPath: '/Users/grace/Project-10/yeahclass-new/private.wxc76296654f49320a.key',
    ignores: ['node_modules/**/*'],
  })

  const result = await ci.upload({
    project,
    version,
    desc: desc || '墨督督学习空间（云托管版）',
    setting: { es6: true, minify: true, autoPrefixWXSS: true },
    onProgressUpdate: console.log,
  })
  console.log('上传完成:', version)
  console.log('包信息:', JSON.stringify(result.subPackageInfo))
}

main().catch((e) => {
  console.error('上传失败:', e.message)
  process.exit(1)
})
