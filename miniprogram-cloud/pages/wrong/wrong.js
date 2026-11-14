const { api, ensureBoot } = require('../../utils/api');
const common = require('../../utils/common');

Page({
    data: {
        state: 'loading',
        errorMsg: '',
        list: [],
        retrying: false,
    },

    onShow() {
        this.load(this.data.state !== 'ready');
    },

    load(showLoading) {
        if (showLoading) {
            this.setData({ state: 'loading', errorMsg: '' });
        }
        ensureBoot()
            .then(() => api('catalog'))
            .then((catalog) => {
                const list = catalog
                    .filter((q) => q.last_correct === false)
                    .map((q, i) => ({
                        id: q.id,
                        number: ('0' + (i + 1)).slice(-2),
                        pills: common.pills(q),
                        prompt: q.prompt,
                        foot: q.material_name + ' · ' + common.lastState(q),
                    }));
                this.setData({ state: 'ready', list: list });
            })
            .catch((err) => {
                this.setData({ state: 'error', errorMsg: err.message });
            });
    },

    handleRetry() {
        this.load(true);
    },

    handleRetryWrong() {
        if (this.data.retrying) {
            return;
        }
        this.setData({ retrying: true });
        api('sessions', { mode: 'wrong', count: 50 })
            .then((s) => {
                wx.navigateTo({ url: '/pages/exercise/exercise?id=' + encodeURIComponent(s.id) });
                if (s.total < s.requested) {
                    wx.showToast({ title: '当前有 ' + s.total + ' 道可用题目', icon: 'none' });
                }
            })
            .catch((err) => {
                wx.showToast({ title: err.message, icon: 'none' });
            })
            .then(() => {
                this.setData({ retrying: false });
            });
    },

    goPractice() {
        wx.navigateTo({ url: '/pages/practice/practice' });
    },
});
