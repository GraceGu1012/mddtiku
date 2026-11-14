const { ensureBoot } = require('./utils/api');

App({
    onLaunch() {
        ensureBoot().catch(() => {});
    },
    globalData: {},
});
