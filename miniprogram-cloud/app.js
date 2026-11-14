const boot = require('./utils/api');

App({
    onLaunch() {
        boot.ensureBoot().catch(() => {});
        // 首次进入展示 3 页引导，之后不再打扰。
        if (!wx.getStorageSync('mdd_guide_seen_v1')) {
            wx.reLaunch({ url: '/pages/guide/guide' });
        }
    },
    globalData: {},
});
