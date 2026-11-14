// 云托管版小程序真机预览：生成二维码，微信扫码直接体验
// 用法: node scripts/ci-preview.mjs [备注]
// 注意：必须先剥离 NODE_OPTIONS（WorkBuddy 会话 shim 会导致 miniprogram-ci
// fork 编译子进程时间歇性 spawn ENOENT），再动态加载依赖。
delete process.env.NODE_OPTIONS

async function main() {
  const { default: ci } = await import('miniprogram-ci')
  const path = await import('node:path')
  const { fileURLToPath } = await import('node:url')

  const scriptDir = path.dirname(fileURLToPath(import.meta.url))
  const root = path.resolve(scriptDir, '..') // mdd-cloudrun 项目根目录
  const project = new ci.Project({
    appid: 'wxc76296654f49320a',
    type: 'miniProgram',
    projectPath: path.join(root, 'miniprogram-cloud'),
    privateKeyPath: '/Users/grace/Project-10/yeahclass-new/private.wxc76296654f49320a.key',
    ignores: ['node_modules/**/*'],
  })

  const result = await ci.preview({
    project,
    desc: process.argv[2] || '云托管链路验证',
    setting: { es6: true, minify: true, autoPrefixWXSS: true },
    qrcodeFormat: 'image',
    qrcodeOutputDest: path.join(root, 'preview-qrcode.jpg'),
    onProgressUpdate: console.log,
  })
  console.log('预览码已生成:', path.join(root, 'preview-qrcode.jpg'))
  console.log('包信息:', JSON.stringify(result.subPackageInfo))
}

main().catch((e) => {
  console.error('预览失败:', e.message)
  process.exit(1)
})
